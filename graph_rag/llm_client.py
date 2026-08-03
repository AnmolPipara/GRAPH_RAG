"""
llm_client.py — Unified LLM Client for the GraphRAG Pipeline.

Provides a single interface to call any OpenAI-compatible API provider
(OpenRouter, OpenAI, Google, Groq) for structured JSON extraction.

All provider-specific logic (base URLs, API keys, response parsing) is
encapsulated here so that extraction/refinement modules remain provider-agnostic.
"""

import json
import re
import logging
from typing import Optional

from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, before_sleep_log

from config.settings import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Configurable LLM client for structured knowledge extraction.

    Supports OpenRouter, OpenAI, Google (Gemini via OpenAI-compatible endpoint),
    and Groq. All providers use the OpenAI client library with custom base URLs.

    Args:
        provider: One of 'openrouter', 'openai', 'google', 'groq'.
        model: Model identifier (e.g., 'nousresearch/hermes-4-405b').
        temperature: Sampling temperature (0.0 = deterministic).
        max_retries: Number of retry attempts on transient failures.
        max_tokens: Maximum tokens in the response.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        temperature: float = 0.0,
        max_retries: int = 3,
        max_tokens: int = 8192,
    ):
        self.provider = provider.lower()
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_tokens = max_tokens

        api_key = settings.get_api_key_for_provider(self.provider)
        base_url = settings.get_base_url_for_provider(self.provider)

        self.client = OpenAI(api_key=api_key, base_url=base_url)

        logger.info(
            f"LLMClient initialized: provider={self.provider}, "
            f"model={self.model}, temperature={self.temperature}"
        )

    # ── Core API Call ───────────────────────────────────────────────────

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[dict] = None,
    ) -> str:
        """Send a chat completion request and return the raw response text.
        Retries on transient errors using exponential backoff via tenacity.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        @retry(
            wait=wait_exponential(multiplier=2, min=4, max=60),
            stop=stop_after_attempt(self.max_retries),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _execute_call():
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format

            response = self.client.chat.completions.create(**kwargs)
            
            if response.usage:
                logger.debug(
                    f"Tokens — prompt: {response.usage.prompt_tokens}, "
                    f"completion: {response.usage.completion_tokens}, "
                    f"total: {response.usage.total_tokens}"
                )
            return response.choices[0].message.content

        try:
            return _execute_call()
        except Exception as e:
            logger.error(f"LLM call failed permanently after {self.max_retries} attempts: {e}")
            raise RuntimeError(f"LLM call failed permanently: {e}")

    # ── JSON Extraction ─────────────────────────────────────────────────

    def extract_json(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        """Call the LLM and parse the response as JSON.

        Attempts to use response_format=json_object where supported.
        Falls back to regex-based JSON extraction if needed.

        Args:
            system_prompt: System-level instruction (should ask for JSON output).
            user_prompt: User message with content to process.

        Returns:
            Parsed dictionary from the model's JSON response.
        """
        # Try with response_format first (supported by OpenAI, OpenRouter, Groq)
        response_format = {"type": "json_object"}

        try:
            raw = self.call(system_prompt, user_prompt, response_format=response_format)
        except Exception:
            # Some models/providers don't support response_format; retry without
            logger.info("response_format not supported, retrying without it")
            raw = self.call(system_prompt, user_prompt)

        return self._parse_json(raw)

    # ── Vision Call (for VLM image extraction) ──────────────────────────

    def call_vision(
        self,
        prompt: str,
        image_base64: str,
        mime_type: str = "image/jpeg",
    ) -> dict:
        """Send an image + text prompt to a vision-language model.

        Args:
            prompt: Text instruction for the VLM.
            image_base64: Base64-encoded image data.
            mime_type: MIME type of the image.

        Returns:
            Parsed JSON dictionary from the VLM response.
        """
        data_uri = f"data:{mime_type};base64,{image_base64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ]

        @retry(
            wait=wait_exponential(multiplier=2, min=4, max=60),
            stop=stop_after_attempt(self.max_retries),
            retry=retry_if_exception_type(Exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _execute_vision_call():
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return self._parse_json(response.choices[0].message.content)

        try:
            return _execute_vision_call()
        except Exception as e:
            logger.error(f"VLM call failed permanently after {self.max_retries} attempts: {e}")
            raise RuntimeError(f"VLM call failed permanently: {e}")

    # ── JSON Parsing Helpers ────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse JSON from LLM response, handling common formatting issues.

        Tries in order:
        1. Direct JSON parse
        2. Extract from markdown code fences
        3. Extract first {...} block via regex
        """
        text = text.strip()

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Extract from code fences: ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. Extract first JSON object
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON from LLM response, returning empty result")
        logger.debug(f"Raw response: {text[:500]}")
        return {"entities": [], "relationships": []}


# ── Factory Functions ───────────────────────────────────────────────────

def get_extraction_client() -> LLMClient:
    """Create an LLM client configured for knowledge extraction."""
    return LLMClient(
        provider=settings.EXTRACTION_PROVIDER,
        model=settings.EXTRACTION_MODEL,
        temperature=settings.EXTRACTION_TEMPERATURE,
        max_retries=settings.EXTRACTION_MAX_RETRIES,
        max_tokens=8192,
    )


def get_refinement_client() -> LLMClient:
    """Create an LLM client configured for graph refinement."""
    return LLMClient(
        provider=settings.REFINEMENT_PROVIDER,
        model=settings.REFINEMENT_MODEL,
        temperature=0.0,
        max_retries=settings.EXTRACTION_MAX_RETRIES,
        max_tokens=8192,
    )


def get_vlm_client() -> LLMClient:
    """Create an LLM client configured for vision-language extraction."""
    return LLMClient(
        provider=settings.VLM_PROVIDER,
        model=settings.VLM_MODEL,
        temperature=0.0,
        max_retries=settings.EXTRACTION_MAX_RETRIES,
        max_tokens=4096,
    )
