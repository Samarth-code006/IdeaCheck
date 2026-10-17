"""Select providers from config and environment without vendor imports elsewhere."""
import os
from functools import lru_cache
from app.config import get_config


@lru_cache(maxsize=1)
def get_llm_provider():
    config=get_config()
    selected=os.getenv("LLM_PROVIDER",config["providers"]["llm"])
    if config["mode"]=="demo":
        selected="fake"
    if config["mode"]=="local-only":
        selected="ollama" if os.getenv("OLLAMA_MODEL") else "fake"
    if selected=="fake":
        from app.providers.llm_fake import FakeLLM
        return FakeLLM()
    if selected=="ollama":
        from app.providers.llm_ollama import OllamaLLM
        return OllamaLLM()
    if selected=="openai_compat":
        from app.providers.llm_openai_compat import OpenAICompatibleLLM
        return OpenAICompatibleLLM(os.getenv("LLM_BASE_URL",config["providers"]["llm_base_url"]),
                                   os.getenv("LLM_MODEL",config["providers"]["llm_model"]),
                                   os.getenv("LLM_API_KEY"),config["providers"]["llm_rpm"])
    raise ValueError("LLM_PROVIDER must be openai_compat, ollama, or fake.")


@lru_cache(maxsize=1)
def get_embedding_provider():
    config=get_config()
    selected=os.getenv("EMBEDDING_PROVIDER",config["providers"]["embedding"])
    if config["mode"] in {"demo","local-only"} and selected=="local":
        selected="tfidf"
    if selected=="local":
        try:
            from app.providers.embed_local import LocalSentenceEmbedder
            return LocalSentenceEmbedder()
        except Exception:
            pass
    from app.providers.embed_tfidf import TfidfEmbedder
    return TfidfEmbedder()
