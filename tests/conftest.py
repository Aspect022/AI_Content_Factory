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
