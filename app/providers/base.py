"""Typed contracts that isolate the orchestrator from provider implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TypeAlias

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """The current ability of a provider to accept a request."""

    available: bool
    checked_at: datetime
    reason: str | None = None


class Provider(Protocol):
    """Common properties available to every provider implementation."""

    name: str
    priority: int

    def health_check(self) -> ProviderHealth:
        """Return whether the provider can currently accept work."""


@dataclass(frozen=True, slots=True)
class TextGenerationRequest:
    """A schema-bound text-generation request passed to a text provider."""

    prompt: str
    schema: JsonObject


@dataclass(frozen=True, slots=True)
class TextGenerationResponse:
    """Structured text output returned by a text provider."""

    content: JsonObject
    model: str


class TextProvider(Provider, Protocol):
    """Contract for providers that generate JSON-backed text content."""

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Generate content that satisfies the request schema."""


@dataclass(frozen=True, slots=True)
class VideoGenerationRequest:
    """Provider-neutral input for a future video generation job."""

    prompt: str
    aspect_ratio: str = "9:16"
    duration_seconds: int = 8


@dataclass(frozen=True, slots=True)
class VideoJob:
    """A provider-owned asynchronous video generation job."""

    job_id: str
    status: str
    model: str


class VideoProvider(Provider, Protocol):
    """Contract for asynchronous video generation providers."""

    def can_accept(self, request: VideoGenerationRequest) -> bool:
        """Return whether the provider accepts this request."""

    def create_job(self, request: VideoGenerationRequest) -> VideoJob:
        """Create a provider-owned video generation job."""

    def poll_job(self, job_id: str) -> VideoJob:
        """Return the current state of a video generation job."""

    def download_result(self, job_id: str, target_path: Path) -> Path:
        """Download a completed job to the requested target path."""


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    """A message and optional local attachment for owner notification."""

    message: str
    attachment: Path | None = None


class NotificationProvider(Provider, Protocol):
    """Contract for delivery of pipeline status notifications."""

    def send(self, request: NotificationRequest) -> None:
        """Deliver a notification request."""


@dataclass(frozen=True, slots=True)
class UploadRequest:
    """Provider-neutral input for a future media upload."""

    video_path: Path
    title: str
    description: str
    tags: tuple[str, ...]
    category_id: str = "22"
    privacy_status: str = "private"


@dataclass(frozen=True, slots=True)
class UploadResponse:
    """The durable identifier and URL supplied by an upload provider."""

    upload_id: str
    url: str


class UploadProvider(Provider, Protocol):
    """Contract for video-upload providers."""

    def upload(self, request: UploadRequest) -> UploadResponse:
        """Upload media and return its provider-owned identifiers."""
