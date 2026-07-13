"""Offline tests for the official Gemini Omni Flash video provider."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.exceptions import ProviderUnavailableError
from app.providers.base import VideoGenerationRequest
from app.providers.gemini_omni_video_provider import GeminiOmniVideoProvider
from app.providers.router import ProviderRouter
from app.providers.veo_provider import VideoHttpResponse
from app.video.generation import VideoGenerationService


def test_gemini_omni_generates_portrait_mp4(tmp_path: Path) -> None:
    """The Interactions response is decoded and saved as a local MP4."""

    calls: list[dict[str, object]] = []

    def transport(
        _method: str,
        _url: str,
        _headers: Mapping[str, str],
        body: bytes | None,
    ) -> VideoHttpResponse:
        calls.append(json.loads(body or b"{}"))
        return VideoHttpResponse(
            200,
            json.dumps(
                {
                    "id": "interaction-1",
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "video",
                                    "mime_type": "video/mp4",
                                    "data": base64.b64encode(b"mp4-bytes").decode(),
                                }
                            ],
                        }
                    ],
                }
            ).encode(),
        )

    provider = GeminiOmniVideoProvider(
        "key",
        name="gemini_omni",
        priority=1,
        model="gemini-omni-flash-preview",
        transport=transport,
    )

    job = provider.create_job(VideoGenerationRequest("A portrait scene"))
    destination = provider.download_result(job.job_id, tmp_path / "video.mp4")

    assert calls[0]["model"] == "gemini-omni-flash-preview"
    assert calls[0]["response_format"] == {"type": "video", "aspect_ratio": "9:16"}
    assert job.status == "completed"
    assert destination.read_bytes() == b"mp4-bytes"


def test_video_service_returns_standardized_local_mp4_result(tmp_path: Path) -> None:
    """The generic service adds no provider-specific details to its result."""

    provider = GeminiOmniVideoProvider(
        "key",
        name="gemini_omni",
        priority=1,
        model="configured",
        transport=lambda *_args: VideoHttpResponse(
            200,
            b'{"id":"v1","steps":[{"content":[{"type":"video","data":"bXA0"}]}]}',
        ),
    )
    result = VideoGenerationService(
        ProviderRouter([provider]), sleep=lambda _: None, poll_interval_seconds=0
    ).generate(VideoGenerationRequest("prompt"), tmp_path / "video.mp4")

    assert result.local_mp4_path == tmp_path / "video.mp4"
    assert result.metadata == {"aspect_ratio": "9:16", "source_image": False}


def test_gemini_omni_uses_image_to_video_input(tmp_path: Path) -> None:
    """A local image is encoded only when the provider receives one."""

    image = tmp_path / "reference.png"
    image.write_bytes(b"png-bytes")
    payloads: list[dict[str, object]] = []

    def transport(
        _method: str,
        _url: str,
        _headers: Mapping[str, str],
        body: bytes | None,
    ) -> VideoHttpResponse:
        payloads.append(json.loads(body or b"{}"))
        return VideoHttpResponse(
            200,
            b'{"id":"image-1","steps":[{"content":[{"type":"video","data":"bXA0"}]}]}',
        )

    provider = GeminiOmniVideoProvider(
        "key", name="gemini_omni", priority=1, model="configured", transport=transport
    )
    provider.create_job(VideoGenerationRequest("Animate it", source_image_path=image))

    assert payloads[0]["generation_config"] == {
        "video_config": {"task": "image_to_video"}
    }
    assert isinstance(payloads[0]["input"], list)


@pytest.mark.parametrize("status_code", [401, 403, 404])
def test_gemini_omni_does_not_mark_permanent_http_failures_retriable(
    status_code: int,
) -> None:
    """Authentication and missing-model responses are permanent failures."""

    provider = GeminiOmniVideoProvider(
        "key",
        name="gemini_omni",
        priority=1,
        model="configured",
        transport=lambda *_args: VideoHttpResponse(status_code, b'{"error":"no"}'),
    )

    with pytest.raises(ProviderUnavailableError) as error:
        provider.create_job(VideoGenerationRequest("prompt"))

    assert error.value.error.retriable is False


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_gemini_omni_marks_only_transient_http_failures_retriable(
    status_code: int,
) -> None:
    """The documented transient status set remains eligible for backoff."""

    provider = GeminiOmniVideoProvider(
        "key",
        name="gemini_omni",
        priority=1,
        model="configured",
        transport=lambda *_args: VideoHttpResponse(status_code, b'{"error":"retry"}'),
    )

    with pytest.raises(ProviderUnavailableError) as error:
        provider.create_job(VideoGenerationRequest("prompt"))

    assert error.value.error.retriable is True
