"""Configuration-driven registration of versioned video provider profiles."""

from __future__ import annotations

from time import sleep

from app.config import AppConfig, VideoProviderProfile
from app.exceptions import ConfigurationError, ErrorInfo
from app.providers.gemini_omni_video_provider import GeminiOmniVideoProvider
from app.providers.openrouter_video_provider import OpenRouterVideoProvider
from app.providers.router import ProviderRouter
from app.providers.veo_provider import VeoVideoProvider
from app.utils.retry import RetryManager, RetryPolicy
from app.video.generation import VideoGenerationService


def build_video_generation_service(configuration: AppConfig) -> VideoGenerationService:
    """Build video providers solely from ordered runtime profile configuration."""

    providers = tuple(
        _build_video_provider(profile)
        for profile in configuration.video_provider_profiles
    )
    router = ProviderRouter(
        providers,
        fallback_allowed=configuration.default_provider_policy == "fallback_allowed",
        retry_manager=RetryManager(
            RetryPolicy(max_retries=2, base_delay_seconds=2.0, multiplier=2.0)
        ),
    )
    return VideoGenerationService(router, sleep=sleep)


def _build_video_provider(profile: VideoProviderProfile) -> object:
    if profile.provider == "gemini_omni":
        return GeminiOmniVideoProvider(
            profile.api_key,
            name=profile.name,
            priority=profile.priority,
            model=profile.model,
        )
    if profile.provider in {"google_flow", "google_veo"}:
        return VeoVideoProvider(
            profile.api_key,
            name=profile.name,
            priority=profile.priority,
            model=profile.model,
        )
    if profile.provider == "openrouter":
        return OpenRouterVideoProvider(
            profile.api_key,
            name=profile.name,
            priority=profile.priority,
            model=profile.model,
        )
    raise ConfigurationError(
        ErrorInfo(
            code="unsupported_video_provider",
            message=f"Unsupported configured video provider: {profile.provider}",
            retriable=False,
            failure_step="configuration",
        )
    )
