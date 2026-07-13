"""Shared fixtures for AI Shorts Factory tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture()
def required_environment() -> dict[str, str]:
    """Return a complete fake environment without any real secrets."""

    return {
        "GROQ_API_KEY": "test-groq-key",
        "NVIDIA_API_KEY": "test-nvidia-key",
        "GEMINI_API_KEY": "test-gemini-key",
        "GEMINI_FALLBACK_API_KEY": "test-gemini-fallback-key",
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "OPENROUTER_FALLBACK_API_KEY": "test-openrouter-fallback-key",
        "VIDEO_PROVIDER_PROFILES_JSON": (
            '[{"name":"flow_quality","provider":"google_flow",'
            '"model":"veo-quality","api_key_env":"GEMINI_API_KEY"},'
            '{"name":"openrouter","provider":"openrouter",'
            '"model":"alibaba/wan-2.6:free","api_key_env":"OPENROUTER_API_KEY"},'
            '{"name":"flow_fallback","provider":"google_flow",'
            '"model":"veo-lite","api_key_env":"GEMINI_FALLBACK_API_KEY"}]'
        ),
        "YOUTUBE_CLIENT_SECRET_JSON": '{"installed": {}}',
        "YOUTUBE_REFRESH_TOKEN": "test-refresh-token",
        "TELEGRAM_BOT_TOKEN": "test-telegram-token",
        "TELEGRAM_CHAT_ID": "123456",
        "GITHUB_TOKEN": "test-github-token",
        "RUN_TIMEZONE": "Asia/Kolkata",
    }


@pytest.fixture()
def project_root(tmp_path: Path) -> Iterator[Path]:
    """Provide an isolated project root for file-system-backed tests."""

    yield tmp_path
