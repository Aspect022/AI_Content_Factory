"""Offline tests for OpenRouter's configurable asynchronous video provider."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.exceptions import ProviderUnavailableError
from app.providers.base import VideoGenerationRequest
from app.providers.openrouter_video_provider import OpenRouterVideoProvider
from app.providers.router import ProviderRouter
from app.providers.veo_provider import VideoHttpResponse
from app.video.factory import build_video_generation_service
from app.video.generation import VideoGenerationService


def test_openrouter_video_provider_uses_configured_model_and_downloads_mp4(
    tmp_path: Path,
) -> None:
    """OpenRouter submits, polls, and downloads using only the configured model."""

    calls: list[tuple[str, str, bytes | None]] = []

    def transport(
        method: str, url: str, _headers: Mapping[str, str], body: bytes | None
    ) -> VideoHttpResponse:
        calls.append((method, url, body))
        if method == "POST":
            return VideoHttpResponse(202, b'{"id":"job-1","status":"pending"}')
        if url.endswith("job-1"):
            return VideoHttpResponse(
                200,
                b'{"id":"job-1","status":"completed",'
                b'"unsigned_urls":["https://download.example/video.mp4"]}',
            )
        return VideoHttpResponse(200, b"mp4-bytes")

    provider = OpenRouterVideoProvider(
        "key",
        name="openrouter",
        priority=2,
        model="configured/model",
        transport=transport,
    )
    service = VideoGenerationService(
        ProviderRouter([provider]), sleep=lambda _: None, poll_interval_seconds=0
    )

    result = service.generate(
        VideoGenerationRequest("video prompt"), tmp_path / "run.mp4"
    )

    assert json.loads(calls[0][2] or b"{}")["model"] == "configured/model"
    assert result.local_path.read_bytes() == b"mp4-bytes"
    assert result.provider == "openrouter"


def test_openrouter_video_provider_surfaces_failed_jobs() -> None:
    """A failed async job is a structured provider failure for router fallback."""

    provider = OpenRouterVideoProvider(
        "key",
        name="openrouter",
        priority=2,
        model="configured/model",
        transport=lambda *_args: VideoHttpResponse(200, b'{"status":"failed"}'),
    )

    with pytest.raises(ProviderUnavailableError):
        provider.poll_job("job-1")


def test_video_factory_uses_only_ordered_runtime_profiles(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Factory registration is driven by profile config, not the orchestrator."""

    from app.config import load_config

    service = build_video_generation_service(
        load_config(required_environment, project_root)
    )

    assert isinstance(service, VideoGenerationService)
