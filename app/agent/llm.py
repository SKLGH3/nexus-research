"""Lazy, provider-neutral language model construction."""

from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model

from app.core.settings import configure_openai_compat_env, get_settings


@lru_cache(maxsize=1)
def get_model():
    """Build the configured chat model only when a research task starts."""
    settings = get_settings()
    if not settings.llm_model:
        raise RuntimeError("未配置 LLM_MODEL，请在 .env 中填写模型名称。")
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，请在 .env 中填写模型密钥。")

    configure_openai_compat_env(settings)
    provider = settings.llm_provider.strip().lower()
    openai_compatible_providers = {
        "openai",
        "deepseek",
        "openai-compatible",
        "openai_compatible",
    }
    options = {}
    model_provider = provider
    if provider in openai_compatible_providers:
        # DeepSeek and many self-hosted gateways expose an OpenAI-compatible API.
        model_provider = "openai"
        options["api_key"] = settings.llm_api_key
        if settings.llm_base_url:
            options["base_url"] = settings.llm_base_url

    return init_chat_model(
        model=settings.llm_model,
        model_provider=model_provider,
        **options,
    )

