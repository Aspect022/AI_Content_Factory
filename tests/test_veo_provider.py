"""Offline lifecycle tests for the single-clip Veo 3.1 Fast adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.exceptions import ProviderResponseError, ProviderUnavailableError
from app.providers.base import VideoGenerationRequest
from app.providers.veo_provider import VeoVideoProvider, VideoHttpResponse


def test_veo_provider_runs_a_single_eight_second_job_lifecycle(tmp_path: Path) -> None:
    """The adapter creates, polls, and downloads one documented Veo operation."""

    requests: list[tuple[str, str, bytes | None]] = []

    def transport(
        method: str, url: str, _headers: Mapping[str, str], body: bytes | None
    ) -> VideoHttpResponse:
        requests.append((method, url, body))
        if method == "POST":
            return VideoHttpResponse(200, b'{"name": "operations/video-1"}')
        if url.endswith("operations/video-1") and len(requests) == 2:
            return VideoHttpResponse(200, b'{"done": false}')
        if url.endswith("operations/video-1"):
            return VideoHttpResponse(
                200,
                b'{"done": true, "response": {"generateVideoResponse": '
                b'{"generatedSamples": [{"video": {"uri": "https://download.example/v.mp4"}}]}}}',
            )
        return VideoHttpResponse(200, b"video-bytes")

    provider = VeoVideoProvider("test-key", transport=transport)
    request = VideoGenerationRequest(prompt="Portrait health animation")

    assert provider.can_accept(request) is True
    job = provider.create_job(request)
    assert job.status == "submitted"
    assert provider.poll_job(job.job_id).status == "running"
    assert provider.poll_job(job.job_id).status == "completed"
    destination = provider.download_result(job.job_id, tmp_path / "video.mp4")

    payload = json.loads(requests[0][2] or b"{}")
    assert payload["parameters"] == {"aspectRatio": "9:16", "durationSeconds": 8}
    assert destination.read_bytes() == b"video-bytes"


def test_veo_provider_rejects_unsupported_v1_request_and_missing_result() -> None:
    """Version 1 accepts only one short portrait clip and validates result metadata."""

    provider = VeoVideoProvider(
        "test-key", transport=lambda *_args: VideoHttpResponse(200, b"{}")
    )

    assert (
        provider.can_accept(VideoGenerationRequest("prompt", duration_seconds=15))
        is False
    )
    with pytest.raises(ProviderUnavailableError):
        provider.create_job(VideoGenerationRequest("prompt", aspect_ratio="16:9"))
    with pytest.raises(ProviderResponseError):
        provider.download_result("operations/missing", Path("video.mp4"))


def test_veo_provider_classifies_invalid_operations_and_completed_errors() -> None:
    """Malformed and failed long-running operations remain structured failures."""

    missing_name = VeoVideoProvider(
        "test-key", transport=lambda *_args: VideoHttpResponse(200, b"{}")
    )
    with pytest.raises(ProviderResponseError):
        missing_name.create_job(VideoGenerationRequest("prompt"))

    failed_operation = VeoVideoProvider(
        "test-key",
        transport=lambda *_args: VideoHttpResponse(
            200, b'{"done": true, "error": {"message": "rejected"}}'
        ),
    )
    with pytest.raises(ProviderUnavailableError):
        failed_operation.poll_job("operations/failed")

    invalid_json = VeoVideoProvider(
        "test-key", transport=lambda *_args: VideoHttpResponse(200, b"not-json")
    )
    with pytest.raises(ProviderResponseError):
        invalid_json.poll_job("operations/invalid")


def test_veo_standard_transport_never_requires_a_real_network_call() -> None:
    """Standard transport paths are covered with a patched opener."""

    class FakeResponse:
        """Minimal binary URL response context manager."""

        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"name": "operations/video"}'

    provider = VeoVideoProvider("test-key")
    with patch("app.providers.veo_provider.urlopen", return_value=FakeResponse()):
        assert (
            provider.create_job(VideoGenerationRequest("prompt")).job_id
            == "operations/video"
        )

    http_error = HTTPError("https://mock.example", 500, "server", None, BytesIO(b"{}"))
    with patch("app.providers.veo_provider.urlopen", side_effect=http_error):
        with pytest.raises(ProviderUnavailableError):
            provider.create_job(VideoGenerationRequest("prompt"))

    with patch("app.providers.veo_provider.urlopen", side_effect=URLError("offline")):
        with pytest.raises(ProviderUnavailableError):
            provider.create_job(VideoGenerationRequest("prompt"))
