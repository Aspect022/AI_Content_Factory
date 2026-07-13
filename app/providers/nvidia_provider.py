"""NVIDIA NIM DeepSeek-R1 adapter using its OpenAI-compatible chat endpoint."""

from __future__ import annotations

from datetime import UTC, datetime

from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.groq_provider import _openai_content
from app.providers.http import HttpTransport, post_json


class NvidiaNimTextProvider:
    """Generate JSON-guided text through NVIDIA NIM DeepSeek-R1."""

    name = "nvidia_nim_deepseek_r1"
    priority = 2
    model = "deepseek-ai/deepseek-r1"
    _endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        *,
        name: str | None = None,
        priority: int | None = None,
        transport: HttpTransport | None = None,
    ) -> None:
        """Create the adapter with runtime configuration and optional test transport."""

        self._api_key = api_key
        self._transport = transport
        if name is not None:
            self.name = name
        if priority is not None:
            self.priority = priority

    def health_check(self) -> ProviderHealth:
        """Report configured readiness without making a remote request."""

        return ProviderHealth(
            available=bool(self._api_key),
            checked_at=datetime.now(UTC),
            reason=None if self._api_key else "NVIDIA_API_KEY is not configured.",
        )

    def generate_json(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """Request one JSON-only completion from the documented NIM endpoint."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{request.prompt}\nReturn only one JSON object.",
                }
            ],
            "stream": False,
        }
        response = post_json(
            self._endpoint,
            {"Authorization": f"Bearer {self._api_key}"},
            payload,
            transport=self._transport,
        )
        return TextGenerationResponse(
            content=_openai_content(response), model=self.model
        )
