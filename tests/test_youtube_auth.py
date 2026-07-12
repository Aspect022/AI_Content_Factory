"""Tests for the local one-time YouTube OAuth credential bootstrap."""

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.exceptions import ConfigurationError
from app.youtube_auth import authorize_youtube


@dataclass
class FakeCredentials:
    refresh_token: str | None


class FakeFlow:
    def __init__(self, refresh_token: str | None) -> None:
        self._credentials = FakeCredentials(refresh_token)
        self.calls: list[dict[str, object]] = []

    def run_local_server(self, **kwargs: object) -> FakeCredentials:
        self.calls.append(kwargs)
        return self._credentials


def test_authorize_youtube_writes_refresh_token_without_printing(
    tmp_path: Path,
) -> None:
    """The local OAuth flow writes a user-chosen ignored credential file."""

    client_file = tmp_path / "client.json"
    client_file.write_text("{}", encoding="utf-8")
    flow = FakeFlow("refresh-token")

    output = authorize_youtube(
        client_file,
        tmp_path / "youtube-token.json",
        flow_factory=lambda _path, _scopes: flow,
    )

    assert '"refresh_token": "refresh-token"' in output.read_text(encoding="utf-8")
    assert flow.calls == [
        {"port": 0, "open_browser": True, "access_type": "offline", "prompt": "consent"}
    ]


def test_authorize_youtube_rejects_missing_input_or_refresh_token(
    tmp_path: Path,
) -> None:
    """Bootstrap failures are structured and do not create a partial secret file."""

    with pytest.raises(ConfigurationError, match="does not exist"):
        authorize_youtube(tmp_path / "missing.json", tmp_path / "output.json")

    client_file = tmp_path / "client.json"
    client_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="refresh token"):
        authorize_youtube(
            client_file,
            tmp_path / "output.json",
            flow_factory=lambda _path, _scopes: FakeFlow(None),
        )
