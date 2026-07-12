"""Composition root for the scheduled daily pipeline."""

from __future__ import annotations

from app.config import AppConfig
from app.content.factory import build_content_generator
from app.logging.logger import RunLogger
from app.orchestrator import DailyOrchestrator
from app.providers.telegram_provider import TelegramNotificationProvider
from app.providers.youtube_provider import YouTubeUploadProvider
from app.video.factory import build_video_generation_service


def build_daily_orchestrator(configuration: AppConfig) -> DailyOrchestrator:
    """Compose runtime services without exposing concrete providers to orchestration."""

    return DailyOrchestrator(
        content_generator=build_content_generator(configuration),
        video_generator=build_video_generation_service(configuration),
        uploader=YouTubeUploadProvider(
            configuration.youtube_client_secret_json,
            configuration.youtube_refresh_token,
        ),
        notifier=TelegramNotificationProvider(
            configuration.telegram_bot_token, configuration.telegram_chat_id
        ),
        run_logger=RunLogger(
            configuration.data_directory / "database.sqlite",
            configuration.data_directory / "runs",
        ),
        temporary_video_directory=configuration.data_directory / "videos",
        youtube_category_id=configuration.youtube_category_id,
        youtube_privacy_status=configuration.youtube_privacy_status,
    )
