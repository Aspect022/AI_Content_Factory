"""Generate and validate one Hindi Shorts topic and script through a router."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template

from app.exceptions import ProviderResponseError, ValidationError
from app.providers.base import JsonObject, TextGenerationRequest, TextProvider
from app.providers.router import ProviderRouter
from app.utils.jsonschema import validate_json_schema

_PROMPT_DIRECTORY = Path(__file__).parents[1] / "prompts"

TOPIC_SCHEMA: JsonObject = {
    "type": "object",
    "required": ["language", "pillar", "topic", "hook", "estimated_seconds"],
    "additionalProperties": False,
    "properties": {
        "language": {"type": "string", "enum": ["hi"]},
        "pillar": {"type": "string", "minLength": 1},
        "topic": {"type": "string", "minLength": 1},
        "hook": {"type": "string", "minLength": 1},
        "estimated_seconds": {"type": "integer", "enum": [15, 16, 17, 18, 19, 20]},
    },
}

SCRIPT_SCHEMA: JsonObject = {
    "type": "object",
    "required": [
        "topic",
        "hook",
        "script",
        "title",
        "description",
        "hashtags",
        "visual_prompt",
        "voice_prompt",
        "safety_notes",
        "estimated_seconds",
    ],
    "additionalProperties": False,
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "hook": {"type": "string", "minLength": 1},
        "script": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "description": {"type": "string", "minLength": 1},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "visual_prompt": {"type": "string", "minLength": 1},
        "voice_prompt": {"type": "string", "minLength": 1},
        "safety_notes": {"type": "array", "items": {"type": "string"}},
        "estimated_seconds": {"type": "integer", "enum": [15, 16, 17, 18, 19, 20]},
    },
}


@dataclass(frozen=True, slots=True)
class Topic:
    """Validated topic output used as input to script generation."""

    language: str
    pillar: str
    topic: str
    hook: str
    estimated_seconds: int


@dataclass(frozen=True, slots=True)
class Script:
    """Validated provider-neutral metadata and creative direction for one Short."""

    topic: str
    hook: str
    script: str
    title: str
    description: str
    hashtags: tuple[str, ...]
    visual_prompt: str
    voice_prompt: str
    safety_notes: tuple[str, ...]
    estimated_seconds: int


class ContentGenerator:
    """Expose topic and script generation without calling providers directly."""

    def __init__(self, router: ProviderRouter[TextProvider]) -> None:
        """Create the service with the configured text-provider router."""

        self._router = router

    def generate_topic(self, pillar: str | None = None) -> Topic:
        """Generate and validate one Hindi health-and-body-explainer topic."""

        content = self._generate(
            _render_prompt(
                "topic_prompt.txt", pillar=pillar or "Choose one listed pillar."
            ),
            TOPIC_SCHEMA,
        )
        return Topic(
            language=str(content["language"]),
            pillar=str(content["pillar"]),
            topic=str(content["topic"]),
            hook=str(content["hook"]),
            estimated_seconds=int(content["estimated_seconds"]),
        )

    def generate_script(self, topic: Topic) -> Script:
        """Generate and validate one complete Hindi Shorts script for a topic."""

        content = self._generate(
            _render_prompt(
                "script_prompt.txt",
                pillar=topic.pillar,
                topic=topic.topic,
                hook=topic.hook,
                estimated_seconds=str(topic.estimated_seconds),
            ),
            SCRIPT_SCHEMA,
        )
        return Script(
            topic=str(content["topic"]),
            hook=str(content["hook"]),
            script=str(content["script"]),
            title=str(content["title"]),
            description=str(content["description"]),
            hashtags=tuple(str(item) for item in content["hashtags"]),  # type: ignore[arg-type]
            visual_prompt=str(content["visual_prompt"]),
            voice_prompt=str(content["voice_prompt"]),
            safety_notes=tuple(str(item) for item in content["safety_notes"]),  # type: ignore[arg-type]
            estimated_seconds=int(content["estimated_seconds"]),
        )

    def _generate(self, prompt: str, schema: JsonObject) -> JsonObject:
        request = TextGenerationRequest(prompt=prompt, schema=schema)

        def operation(provider: TextProvider) -> JsonObject:
            response = provider.generate_json(request)
            try:
                validate_json_schema(response.content, schema)
            except ValidationError as error:
                raise ProviderResponseError.from_message(
                    code="provider_contract_invalid",
                    message="The provider output did not satisfy the requested schema.",
                    retriable=True,
                    failure_step=error.error.failure_step,
                ) from error
            return response.content

        return self._router.execute(operation).value


def _render_prompt(name: str, **values: str) -> str:
    """Load a versioned prompt template and substitute its named placeholders."""

    return Template((_PROMPT_DIRECTORY / name).read_text(encoding="utf-8")).substitute(
        values
    )
