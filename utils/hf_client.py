"""
hf_client.py — Reasoning-aware ChatModel for the HuggingFace Inference Router.

HuggingFace Inference Router serves reasoning models (e.g. Qwen3.5-397B-A17B)
whose responses include a `reasoning` field alongside `content`. LangChain's
ChatOpenAI mishandles these responses (empty content + a `refusal` key), so we
provide a minimal BaseChatModel subclass that calls the router's OpenAI-
compatible endpoint directly and extracts `content` correctly.

IMPORTANT: the router bills per token against the account's included credits.
A single 397B reasoning call with max_tokens=8192 can take 30-60s and consume
a large chunk of the monthly free allowance.
"""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

logger = logging.getLogger(__name__)

HF_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"

# Reasoning models burn a huge thinking budget by default (a probe took ~46s
# and ~18K chars of reasoning). "low" cuts that to ~4s and ~300 tokens with
# negligible quality loss for Cypher/QA generation — essential for a 200+
# call benchmark run to be affordable on included credits.
DEFAULT_REASONING_EFFORT = "low"


class HFReasoningChatModel(BaseChatModel):
    """Chat model for HF Inference Router reasoning models (Qwen3.5 etc.).

    Implements the LangChain BaseChatModel interface so it works with
    GraphCypherQAChain, LCEL pipelines, and the shared fair-LLM path.
    """

    model: str = "Qwen/Qwen3.5-397B-A17B"
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096  # headroom for thinking + answer
    reasoning_effort: str = DEFAULT_REASONING_EFFORT
    # MEASURED: with thinking enabled, hard questions burned the full 4096-token
    # output budget (~$0.012/call at DeepInfra's $3.00/M output) and the free
    # $0.10/month included-credit allowance died in ~4 calls. Setting
    # enable_thinking=False and routing via the router's ":cheapest" flag
    # (DeepInfra) cut a real QA call to ~333 output tokens / ~$0.001 — roughly
    # 12x cheaper, still correct — which makes the 10-question smoke and even
    # short runs affordable on the free tier.
    enable_thinking: bool = False
    routing_suffix: str = ":cheapest"
    timeout: int = 600

    @property
    def _llm_type(self) -> str:
        return "hf-reasoning"

    def _messages_to_prompt(self, messages: List[BaseMessage]) -> str:
        parts = []
        for m in messages:
            if isinstance(m, SystemMessage):
                parts.append(f"[System]\n{m.content}")
            elif isinstance(m, HumanMessage):
                parts.append(f"[User]\n{m.content}")
            else:
                parts.append(str(getattr(m, "content", "")))
        return "\n\n".join(parts)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = self._messages_to_prompt(messages)
        body: Dict[str, Any] = {
            "model": self.model + self.routing_suffix,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "enable_thinking": self.enable_thinking,
        }
        if stop:
            body["stop"] = stop

        req = urllib.request.Request(
            HF_ROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            logger.error("HF Router HTTP %s: %s", e.code, detail)
            raise RuntimeError(f"HF Router HTTP {e.code}: {detail}")
        except Exception as e:
            logger.error("HF Router request failed: %s", e)
            raise RuntimeError(f"HF Router request failed: {e}")

        try:
            message = out["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected HF Router response: {str(out)[:300]}") from e

        content = message.get("content") or ""
        # Reasoning models occasionally exhaust the token budget on thinking and
        # return content="" — surface that as an explicit error so the evaluator
        # records a diagnosable failure instead of a silent empty answer.
        if not content.strip() and message.get("reasoning"):
            raise RuntimeError(
                "HF model returned no content (reasoning consumed the token budget); "
                "retry with a larger max_tokens"
            )

        # Expose exact token usage so evaluation runs can track per-call credit
        # burn (the router bills per token against monthly included credits).
        llm_output = {"token_usage": out.get("usage", {})}
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=content))],
            llm_output=llm_output,
        )


def get_hf_model(model: Optional[str] = None, max_tokens: Optional[int] = None,
                 api_key: str = "") -> HFReasoningChatModel:
    """Factory helper returning a configured HFReasoningChatModel."""
    from config.settings import settings

    kwargs: Dict[str, Any] = {
        "model": model or settings.huggingface_model,
        "api_key": api_key or settings.huggingface_api_key,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return HFReasoningChatModel(**kwargs)
