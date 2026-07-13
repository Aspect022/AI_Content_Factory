"""Tests for routed topic and script generation with mock text providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.config import load_config
from app.content.factory import build_content_generator
from app.content.generation import ContentGenerator, Topic
from app.providers.base import (
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResponse,
)
from app.providers.router import ProviderRouter
from app.utils.retry import RetryManager, RetryPolicy


@dataclass
class MockTextProvider:
    """A queue-backed test provider with no network behavior."""

    name: str
    priority: int
    outputs: list[dict[str, object]]
    calls: int = field(default=0, init=False)

    def health_check(self) -> ProviderHealth:
        """Always make the mock available."""

        return ProviderHealth(available=True, checked_at=datetime.now(UTC))

    def generate_json(self, _request: TextGenerationRequest) -> TextGenerationResponse:
        """Return the next deterministic JSON object."""

        self.calls += 1
        return TextGenerationResponse(content=self.outputs.pop(0), model="mock-model")


TOPIC = {
    "language": "hi",
    "pillar": "Sleep",
    "topic": "फोन की रोशनी और नींद",
    "hook": "सोने से पहले फोन आपका दिमाग जगाए रख सकता है।",
    "estimated_seconds": 18,
}
SCRIPT = {
    "topic": TOPIC["topic"],
    "hook": TOPIC["hook"],
    "script": "फोन की तेज रोशनी शरीर को दिन जैसा संकेत दे सकती है।",
    "title": "फोन और नींद",
    "description": "नींद की छोटी जानकारी #shorts",
    "hashtags": ["#shorts", "#hindi"],
    "visual_prompt": "रात में फोन देखते व्यक्ति का क्लोज़-अप",
    "voice_prompt": "शांत, स्पष्ट हिंदी आवाज़",
    "safety_notes": ["यह सामान्य शिक्षा है, निदान नहीं।"],
    "estimated_seconds": 18,
}


def test_content_generator_returns_validated_topic_and_script() -> None:
    """The service reaches the provider only through the configured router."""

    provider = MockTextProvider("mock", 1, [TOPIC, SCRIPT])
    generator = ContentGenerator(ProviderRouter([provider]))

    topic = generator.generate_topic("Sleep")
    script = generator.generate_script(topic)

    assert topic == Topic(**TOPIC)
    assert script.title == "फोन और नींद"
    assert script.hashtags == ("#shorts", "#hindi")
    assert provider.calls == 2


def test_content_generator_retries_invalid_output_then_falls_back() -> None:
    """An invalid primary response is retried once before the next provider is used."""

    primary = MockTextProvider("primary", 1, [{"topic": "missing contract"}] * 2)
    fallback = MockTextProvider("fallback", 2, [TOPIC])
    router = ProviderRouter(
        [primary, fallback],
        retry_manager=RetryManager(
            RetryPolicy(max_retries=1, base_delay_seconds=0), sleep=lambda _: None
        ),
    )

    topic = ContentGenerator(router).generate_topic()

    assert topic.topic == TOPIC["topic"]
    assert primary.calls == 2
    assert fallback.calls == 1


def test_content_factory_composes_the_configured_text_provider_chain(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Composition uses configuration only and does not call a provider eagerly."""

    generator = build_content_generator(load_config(required_environment, project_root))

    assert isinstance(generator, ContentGenerator)


def test_content_factory_composes_with_groq_fallback(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Composition includes Groq fallback if GROQ_API_FALLBACK is configured."""

    env = dict(required_environment)
    env["GROQ_API_FALLBACK"] = "test-fallback-key"
    generator = build_content_generator(load_config(env, project_root))

    assert isinstance(generator, ContentGenerator)
    # Ensure there are 3 providers registered in the router
    assert len(generator._router._providers) == 3
    assert generator._router._providers[0].name == "groq_llama_3_3_70b"
    assert generator._router._providers[1].name == "groq_llama_3_3_70b_fallback"
    assert generator._router._providers[2].name == "nvidia_nim_deepseek_r1"
