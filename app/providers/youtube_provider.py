"""Official YouTube Data API uploader using Google client libraries."""

from __future__ import annotations

import json

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.exceptions import UploadError
from app.providers.base import ProviderHealth, UploadRequest, UploadResponse


class YouTubeUploadProvider:
    """Upload one local MP4 through YouTube's official resumable API client."""

    name = "youtube_data_api"
    priority = 1

    def __init__(self, client_secret_json: str, refresh_token: str) -> None:
        """Create an OAuth-backed uploader without persisting credentials."""

        self._client_secret_json = client_secret_json
        self._refresh_token = refresh_token

    def health_check(self) -> ProviderHealth:
        """Report local credential readiness without calling YouTube."""

        from datetime import UTC, datetime

        return ProviderHealth(
            available=bool(self._client_secret_json and self._refresh_token),
            checked_at=datetime.now(UTC),
            reason=(
                None
                if self._client_secret_json and self._refresh_token
                else "OAuth is missing."
            ),
        )

    def upload(self, request: UploadRequest) -> UploadResponse:
        """Upload an MP4 and return only after YouTube returns a video identifier."""

        if not request.video_path.is_file():
            raise UploadError.from_message(
                code="video_file_missing",
                message="The video file to upload does not exist.",
                retriable=False,
                failure_step="youtube_upload",
            )
        try:
            secret = json.loads(self._client_secret_json)
            oauth = secret.get("installed") or secret.get("web")
            credentials = Credentials(
                token=None,
                refresh_token=self._refresh_token,
                token_uri=oauth["token_uri"],
                client_id=oauth["client_id"],
                client_secret=oauth["client_secret"],
            )
            youtube = build(
                "youtube", "v3", credentials=credentials, cache_discovery=False
            )
            description = request.description
            if "#shorts" not in description.lower():
                description = f"{description}\n#shorts"
            tags = list(dict.fromkeys((*request.tags, "#shorts")))
            insert = youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": request.title,
                        "description": description,
                        "tags": tags,
                        "categoryId": request.category_id,
                    },
                    "status": {"privacyStatus": request.privacy_status},
                },
                media_body=MediaFileUpload(
                    str(request.video_path), mimetype="video/mp4", resumable=True
                ),
            )
            response = None
            while response is None:
                _, response = insert.next_chunk()
            video_id = None if response is None else response.get("id")
        except (HttpError, KeyError, TypeError, ValueError) as error:
            raise UploadError.from_message(
                code="youtube_upload_failed",
                message="YouTube rejected or could not complete the upload.",
                retriable=(
                    isinstance(error, HttpError)
                    and error.resp.status in {429, 500, 502, 503, 504}
                ),
                failure_step="youtube_upload",
            ) from error
        if not isinstance(video_id, str) or not video_id:
            raise UploadError.from_message(
                code="youtube_upload_unconfirmed",
                message="YouTube did not confirm an uploaded video ID.",
                retriable=True,
                failure_step="youtube_upload",
            )
        return UploadResponse(
            upload_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}"
        )
