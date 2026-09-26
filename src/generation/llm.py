"""LLM factory: any OpenAI-compatible chat endpoint, configured through settings / .env."""

from langchain_core.language_models import BaseChatModel

from src.config import Settings, get_settings


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    settings = settings or get_settings()

    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key "
            "(and OPENAI_BASE_URL if you use a gateway)."
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        temperature=0,
    )
