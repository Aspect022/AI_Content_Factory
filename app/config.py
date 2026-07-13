"""Environment-only runtime configuration with secret-safe validation."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from app.exceptions import ConfigurationError, ErrorInfo

REQUIRED_ENVIRONMENT_VARIABLES = (
    "GROQ_API_KEY",
    "NVIDIA_API_KEY",
    "GEMINI_API_KEY",
    "GEMINI_FALLBACK_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENROUTER_FALLBACK_API_KEY",
    "VIDEO_PROVIDER_PROFILES_JSON",
    "YOUTUBE_CLIENT_SECRET_JSON",
    "YOUTUBE_REFRESH_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "RUN_TIMEZONE",
)

_VALID_PROVIDER_POLICIES = frozenset({"primary_only", "fallback_allowed"})


@dataclass(frozen=True, slots=True)
class VideoProviderProfile:
    """Configuration-only registration for one selectable video provider."""

    name: str
    provider: str
    model: str
    api_key: str = field(repr=False)
    priority: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated configuration required by the cloud runtime."""

    groq_api_key: str = field(repr=False)
    nvidia_api_key: str = field(repr=False)
    gemini_api_key: str = field(repr=False)
    gemini_fallback_api_key: str = field(repr=False)
    openrouter_api_key: str = field(repr=False)
    openrouter_fallback_api_key: str = field(repr=False)
    youtube_client_secret_json: str = field(repr=False)
    youtube_refresh_token: str = field(repr=False)
    telegram_bot_token: str = field(repr=False)
    telegram_chat_id: str = field(repr=False)
    run_timezone: str
    qwen_api_key: str | None = field(repr=False)
    dreamina_api_key: str | None = field(repr=False)
    whisper_model_size: str | None
    default_language: str
    default_provider_policy: str
    video_duration_seconds: int
    video_provider_profiles: tuple[VideoProviderProfile, ...]
    youtube_category_id: str
    youtube_privacy_status: str
    data_directory: Path

    def redacted_summary(self) -> dict[str, object]:
        """Return non-secret configuration safe for structured logs."""

        return {
            "run_timezone": self.run_timezone,
            "default_language": self.default_language,
            "default_provider_policy": self.default_provider_policy,
            "video_duration_seconds": self.video_duration_seconds,
            "video_provider_order": [
                profile.name for profile in self.video_provider_profiles
            ],
            "youtube_category_id": self.youtube_category_id,
            "youtube_privacy_status": self.youtube_privacy_status,
            "qwen_configured": self.qwen_api_key is not None,
            "dreamina_configured": self.dreamina_api_key is not None,
            "whisper_model_size": self.whisper_model_size,
            "data_directory": str(self.data_directory),
        }


def load_config(
    environment: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> AppConfig:
    """Load and validate configuration exclusively from environment variables.

    Args:
        environment: Optional environment mapping, primarily for tests.
        project_root: Repository root used only to locate the specified data folder.

    Raises:
        ConfigurationError: If a required variable is missing or invalid.
    """

    values = os.environ if environment is None else environment
    missing = [
        name
        for name in REQUIRED_ENVIRONMENT_VARIABLES
        if not values.get(name, "").strip()
    ]
    if missing:
        names = ", ".join(missing)
        raise ConfigurationError(
            ErrorInfo(
                code="missing_required_configuration",
                message=f"Missing required environment variables: {names}",
                retriable=False,
                failure_step="configuration",
            )
        )

    timezone = values["RUN_TIMEZONE"].strip()
    if timezone != "Asia/Kolkata":
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_run_timezone",
                message="RUN_TIMEZONE must be Asia/Kolkata",
                retriable=False,
                failure_step="configuration",
            )
        )

    policy = values.get("DEFAULT_PROVIDER_POLICY", "fallback_allowed").strip()
    if policy not in _VALID_PROVIDER_POLICIES:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_provider_policy",
                message=(
                    "DEFAULT_PROVIDER_POLICY must be primary_only or "
                    "fallback_allowed"
                ),
                retriable=False,
                failure_step="configuration",
            )
        )

    video_duration_seconds = _video_duration(values)
    video_provider_profiles = _video_provider_profiles(values)
    privacy_status = values.get("YOUTUBE_PRIVACY_STATUS", "private").strip()
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_youtube_privacy_status",
                message="YOUTUBE_PRIVACY_STATUS must be private, unlisted, or public",
                retriable=False,
                failure_step="configuration",
            )
        )

    root = (project_root or Path.cwd()).resolve()
    return AppConfig(
        groq_api_key=values["GROQ_API_KEY"].strip(),
        nvidia_api_key=values["NVIDIA_API_KEY"].strip(),
        gemini_api_key=values["GEMINI_API_KEY"].strip(),
        gemini_fallback_api_key=values["GEMINI_FALLBACK_API_KEY"].strip(),
        openrouter_api_key=values["OPENROUTER_API_KEY"].strip(),
        openrouter_fallback_api_key=values["OPENROUTER_FALLBACK_API_KEY"].strip(),
        youtube_client_secret_json=values["YOUTUBE_CLIENT_SECRET_JSON"].strip(),
        youtube_refresh_token=values["YOUTUBE_REFRESH_TOKEN"].strip(),
        telegram_bot_token=values["TELEGRAM_BOT_TOKEN"].strip(),
        telegram_chat_id=values["TELEGRAM_CHAT_ID"].strip(),
        run_timezone=timezone,
        qwen_api_key=_optional_value(values, "QWEN_API_KEY"),
        dreamina_api_key=_optional_value(values, "DREAMINA_API_KEY"),
        whisper_model_size=_optional_value(values, "WHISPER_MODEL_SIZE"),
        default_language=values.get("DEFAULT_LANGUAGE", "hi").strip() or "hi",
        default_provider_policy=policy,
        video_duration_seconds=video_duration_seconds,
        video_provider_profiles=video_provider_profiles,
        youtube_category_id=values.get("YOUTUBE_CATEGORY_ID", "22").strip() or "22",
        youtube_privacy_status=privacy_status,
        data_directory=root / "data",
    )


def _optional_value(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None


def _video_duration(values: Mapping[str, str]) -> int:
    """Load the single-clip Version 1 duration supported by Veo."""

    raw_value = values.get("VIDEO_DURATION_SECONDS", "8").strip()
    try:
        duration = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_video_duration",
                message="VIDEO_DURATION_SECONDS must be 4, 6, or 8",
                retriable=False,
                failure_step="configuration",
            )
        ) from error
    if duration not in {4, 6, 8}:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_video_duration",
                message="VIDEO_DURATION_SECONDS must be 4, 6, or 8",
                retriable=False,
                failure_step="configuration",
            )
        )
    return duration


def _video_provider_profiles(
    values: Mapping[str, str],
) -> tuple[VideoProviderProfile, ...]:
    """Resolve ordered, credential-isolated video profiles from JSON configuration."""

    try:
        raw_profiles = json.loads(values["VIDEO_PROVIDER_PROFILES_JSON"])
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_video_provider_profiles",
                message="VIDEO_PROVIDER_PROFILES_JSON must be valid JSON.",
                retriable=False,
                failure_step="configuration",
            )
        ) from error
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ConfigurationError(
            ErrorInfo(
                code="invalid_video_provider_profiles",
                message="VIDEO_PROVIDER_PROFILES_JSON must contain a non-empty list.",
                retriable=False,
                failure_step="configuration",
            )
        )

    profiles: list[VideoProviderProfile] = []
    names: set[str] = set()
    for priority, raw_profile in enumerate(raw_profiles, start=1):
        if not isinstance(raw_profile, dict):
            raise _invalid_video_profile()
        name = raw_profile.get("name")
        provider = raw_profile.get("provider")
        model = raw_profile.get("model")
        api_key_env = raw_profile.get("api_key_env")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (name, provider, model, api_key_env)
        ):
            raise _invalid_video_profile()
        if name in names:
            raise _invalid_video_profile()
        api_key = values.get(api_key_env, "").strip()
        if not api_key:
            raise ConfigurationError(
                ErrorInfo(
                    code="missing_video_provider_credential",
                    message=(
                        "Missing credential referenced by video profile: "
                        f"{api_key_env}"
                    ),
                    retriable=False,
                    failure_step="configuration",
                )
            )
        names.add(name)
        profiles.append(
            VideoProviderProfile(
                name=name,
                provider=provider,
                model=model,
                api_key=api_key,
                priority=priority,
            )
        )
    return tuple(profiles)


def _invalid_video_profile() -> ConfigurationError:
    """Create the shared structured error for malformed provider profile data."""

    return ConfigurationError(
        ErrorInfo(
            code="invalid_video_provider_profiles",
            message=(
                "Each video provider profile needs unique name, provider, model, "
                "and api_key_env strings."
            ),
            retriable=False,
            failure_step="configuration",
        )
    )
