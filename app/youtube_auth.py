"""One-time local OAuth bootstrap for the YouTube Data API."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.exceptions import ConfigurationError, ErrorInfo

YOUTUBE_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)


class OAuthCredentials(Protocol):
    """Minimal credential data returned by Google's installed-app OAuth flow."""

    refresh_token: str | None

    def to_json(self) -> str:
        """Serialize credentials for a local bootstrap secret file."""


OAuthFlowFactory = Callable[[str, tuple[str, ...]], object]


def authorize_youtube(
    client_secrets_file: Path,
    token_output_file: Path,
    *,
    flow_factory: OAuthFlowFactory | None = None,
) -> Path:
    """Open browser consent and securely store a refresh-token credential file.

    This bootstrap is intentionally local and interactive. Runtime code continues
    to obtain its refresh token from the ``YOUTUBE_REFRESH_TOKEN`` environment
    variable or GitHub Actions secrets.
    """

    if not client_secrets_file.is_file():
        raise ConfigurationError(
            ErrorInfo(
                code="youtube_client_secret_file_missing",
                message="The supplied YouTube OAuth client JSON file does not exist.",
                retriable=False,
                failure_step="youtube_auth",
            )
        )
    factory = flow_factory or _google_flow_factory
    flow = factory(str(client_secrets_file), YOUTUBE_OAUTH_SCOPES)
    credentials = flow.run_local_server(  # type: ignore[attr-defined]
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )
    if not credentials.refresh_token:
        raise ConfigurationError(
            ErrorInfo(
                code="youtube_refresh_token_missing",
                message="Google consent did not return a refresh token.",
                retriable=False,
                failure_step="youtube_auth",
            )
        )
    token_output_file.parent.mkdir(parents=True, exist_ok=True)
    token_output_file.write_text(
        json.dumps(
            {
                "refresh_token": credentials.refresh_token,
                "scopes": list(YOUTUBE_OAUTH_SCOPES),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(token_output_file, 0o600)
    except OSError:
        pass
    return token_output_file


def _google_flow_factory(client_secrets_file: str, scopes: tuple[str, ...]) -> object:
    """Load the official OAuth installed-app flow lazily for CLI-only use."""

    from google_auth_oauthlib.flow import InstalledAppFlow

    return InstalledAppFlow.from_client_secrets_file(client_secrets_file, scopes=scopes)
