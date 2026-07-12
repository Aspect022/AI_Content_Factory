"""Tests for dependency-free provider output schema validation."""

from __future__ import annotations

import re

import pytest

from app.exceptions import ValidationError
from app.utils.jsonschema import validate_json_schema

SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["title", "hashtags", "estimated_seconds"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 80},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "estimated_seconds": {"type": "integer", "enum": [15, 18, 20]},
    },
}


def test_validate_json_schema_accepts_a_supported_valid_contract() -> None:
    """Valid nested output passes without adding a third-party dependency."""

    validate_json_schema(
        {"title": "Sleep tip", "hashtags": ["#shorts"], "estimated_seconds": 18},
        SCHEMA,
    )


@pytest.mark.parametrize(
    ("payload", "path_fragment"),
    [
        ({"title": "x", "hashtags": []}, "missing required property"),
        (
            {"title": "x", "hashtags": [], "estimated_seconds": 18, "extra": True},
            "unexpected property",
        ),
        ({"title": "", "hashtags": [], "estimated_seconds": 18}, "$.title"),
        ({"title": "x", "hashtags": [1], "estimated_seconds": 18}, "$.hashtags[0]"),
        ({"title": "x", "hashtags": [], "estimated_seconds": 16}, "not in enum"),
    ],
)
def test_validate_json_schema_reports_structured_contract_failures(
    payload: dict[str, object], path_fragment: str
) -> None:
    """Every invalid contract is surfaced as a typed validation error."""

    with pytest.raises(ValidationError, match=re.escape(path_fragment)):
        validate_json_schema(payload, SCHEMA)


def test_validate_json_schema_rejects_invalid_schema_definitions() -> None:
    """Unsupported schema setup fails clearly rather than silently accepting data."""

    with pytest.raises(TypeError, match="unsupported schema type"):
        validate_json_schema("value", {"type": "date"})
    with pytest.raises(TypeError, match="type must be a string"):
        validate_json_schema("value", {"type": 1})
    with pytest.raises(TypeError, match="required must be a list"):
        validate_json_schema({}, {"type": "object", "required": "title"})
    with pytest.raises(TypeError, match="properties must be an object"):
        validate_json_schema({}, {"type": "object", "properties": []})
    with pytest.raises(TypeError, match="property 'title'"):
        validate_json_schema(
            {"title": "valid"},
            {"type": "object", "properties": {"title": "string"}},
        )
    with pytest.raises(TypeError, match="items must be an object"):
        validate_json_schema(["valid"], {"type": "array", "items": "string"})


def test_validate_json_schema_supports_scalar_types_and_maximum_length() -> None:
    """The supported scalar types validate without treating booleans as numbers."""

    validate_json_schema(1, {"type": "integer"})
    validate_json_schema(1.5, {"type": "number"})
    validate_json_schema(True, {"type": "boolean"})
    validate_json_schema(None, {"type": "null"})

    with pytest.raises(ValidationError, match="at most 3"):
        validate_json_schema("four", {"type": "string", "maxLength": 3})
    with pytest.raises(ValidationError, match="expected integer"):
        validate_json_schema(True, {"type": "integer"})
