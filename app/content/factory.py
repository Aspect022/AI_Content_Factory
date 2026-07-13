"""Composition root for the concrete text provider chain."""

from __future__ import annotations

from app.config import AppConfig
from app.content.generation import ContentGenerator
from app.providers.base import TextProvider
from app.providers.gemini_provider import GeminiTextProvider
from app.providers.groq_provider import GroqTextProvider
from app.providers.nvidia_provider import NvidiaNimTextProvider
from app.providers.router import ProviderRouter
from app.utils.retry import RetryManager, RetryPolicy


def build_content_generator(configuration: AppConfig) -> ContentGenerator:
    """Build the configured Groq-to-NVIDIA-to-Gemini text provider chain."""

    providers: list[TextProvider] = []
    if configuration.groq_api_key:
        providers.append(GroqTextProvider(configuration.groq_api_key))
    if configuration.nvidia_api_key:
        providers.append(NvidiaNimTextProvider(configuration.nvidia_api_key))
    if configuration.gemini_api_key:
        providers.append(GeminiTextProvider(configuration.gemini_api_key))
    router = ProviderRouter(
        providers,
        fallback_allowed=configuration.default_provider_policy == "fallback_allowed",
        retry_manager=RetryManager(RetryPolicy(max_retries=1)),
    )
    return ContentGenerator(router)
