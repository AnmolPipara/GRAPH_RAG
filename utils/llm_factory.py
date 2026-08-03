from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

class LLMFactory:
    """
    Factory to instantiate the appropriate LLM based on configuration.
    
    Theory:
    Using LangChain's BaseChatModel interface allows us to swap underlying 
    providers (Google, OpenAI, Groq) without changing any pipeline logic.
    """
    
    @staticmethod
    def get_llm() -> BaseChatModel:
        provider = settings.llm_provider.lower()
        
        logger.info(f"Initializing LLM from provider: {provider}")
        
        if provider == "gemini":
            if not settings.google_api_key:
                raise ValueError("GOOGLE_API_KEY environment variable is not set.")
            return ChatOpenAI(
                model=settings.gemini_model,
                temperature=settings.temperature,
                api_key=settings.google_api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            
        elif provider == "openai":
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY environment variable is not set.")
            return ChatOpenAI(
                model=settings.openai_model,
                temperature=settings.temperature,
                api_key=settings.openai_api_key
            )
        elif provider == "huggingface":
            if not settings.huggingface_api_key:
                raise ValueError("HUGGINGFACE_API_KEY environment variable is not set.")
            from utils.hf_client import get_hf_model
            return get_hf_model(api_key=settings.huggingface_api_key)

        elif provider == "openrouter":
            if not settings.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable is not set.")
            return ChatOpenAI(
                api_key=settings.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                model=settings.openrouter_model,
                temperature=settings.temperature
            )
            
        elif provider == "groq":
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY environment variable is not set.")
            # Groq sits behind Cloudflare which blocks python urllib/httpx
            # default user-agents (HTTP 403 error 1010). A browser-like UA
            # keeps calls flowing — same workaround as graph_rag/retriever.py
            # and evaluation/evaluator_v2.py.
            return ChatOpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
                model=settings.groq_model,
                temperature=settings.temperature,
                default_headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                },
            )
            
        # Add HuggingFace support here as needed
        else:
            raise ValueError(f"Unsupported LLM Provider: {provider}")
