"""Mock-backed tests for official YouTube upload and Telegram notification adapters."""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.exceptions import NotificationError, UploadError
from app.providers.base import NotificationRequest, UploadRequest
from app.providers.telegram_provider import TelegramNotificationProvider
from app.providers.youtube_provider import YouTubeUploadProvider


def test_youtube_uploader_returns_confirmed_url_and_adds_shorts(tmp_path: Path) -> None:
    """The official client is called with the local MP4 and complete metadata."""

    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")
    captured: dict[str, object] = {}

    class Insert:
        def next_chunk(self) -> tuple[None, dict[str, str]]:
            return None, {"id": "video-id"}

    class Videos:
        def insert(self, **kwargs: object) -> Insert:
            captured.update(kwargs)
            return Insert()

    class YouTube:
        def videos(self) -> Videos:
            return Videos()

    secret = '{"installed":{"token_uri":"https://token","client_id":"id","client_secret":"secret"}}'
    with (
        patch("app.providers.youtube_provider.build", return_value=YouTube()),
        patch("app.providers.youtube_provider.MediaFileUpload"),
    ):
        result = YouTubeUploadProvider(secret, "refresh").upload(
            UploadRequest(video, "Title", "Description", ("#health",))
        )

    body = captured["body"]
    assert result.url.endswith("video-id")
    assert body["snippet"]["description"].endswith("#shorts")  # type: ignore[index]
    assert "#shorts" in body["snippet"]["tags"]  # type: ignore[index]


def test_youtube_uploader_rejects_missing_video(tmp_path: Path) -> None:
    """No client call occurs when the local handoff file is absent."""

    with pytest.raises(UploadError, match="does not exist"):
        YouTubeUploadProvider("{}", "refresh").upload(
            UploadRequest(tmp_path / "missing.mp4", "Title", "Description", ())
        )


def test_telegram_notifier_sends_and_classifies_failures() -> None:
    """Telegram payload delivery is isolated and returns typed failures."""

    class Response:
        status = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    notifier = TelegramNotificationProvider("token", "chat")
    with patch("app.providers.telegram_provider.urlopen", return_value=Response()):
        notifier.send(NotificationRequest("Uploaded"))

    with patch("app.providers.telegram_provider.urlopen", side_effect=TimeoutError()):
        with pytest.raises(NotificationError):
            notifier.send(NotificationRequest("Failed"))
