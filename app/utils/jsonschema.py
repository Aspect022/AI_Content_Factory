"""Small, dependency-free JSON-schema validator for provider output contracts."""

from __future__ import annotations

from collections.abc import Mapping

from app.exceptions import ErrorInfo, ValidationError


def validate_json_schema(payload: object, schema: Mapping[str, object]) -> None:
    """Validate a JSON-compatible payload against the supported schema subset.

    Supported keywords are ``type``, ``required``, ``properties``,
    ``additionalProperties``, ``items``, ``enum``, ``minLength``, and
    ``maxLength``. A ``ValidationError`` includes the failing JSON path.
    """

    _validate(payload, schema, "$")


def _validate(payload: object, schema: Mapping[str, object], path: str) -> None:
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(payload, expected_type):
        _fail(path, f"expected {expected_type}")

    allowed_values = schema.get("enum")
    if allowed_values is not None and payload not in allowed_values:
        _fail(path, "value is not in enum")

    if isinstance(payload, dict):
        _validate_object(payload, schema, path)
    elif isinstance(payload, list):
        _validate_array(payload, schema, path)
    elif isinstance(payload, str):
        _validate_string(payload, schema, path)


def _matches_type(payload: object, expected_type: object) -> bool:
    if not isinstance(expected_type, str):
        raise TypeError("schema type must be a string")
    return {
        "object": lambda: isinstance(payload, dict),
        "array": lambda: isinstance(payload, list),
        "string": lambda: isinstance(payload, str),
        "integer": lambda: isinstance(payload, int) and not isinstance(payload, bool),
        "number": lambda: isinstance(payload, (int, float))
        and not isinstance(payload, bool),
        "boolean": lambda: isinstance(payload, bool),
        "null": lambda: payload is None,
    }.get(expected_type, lambda: _unsupported_type(expected_type))()


def _validate_object(
    payload: dict[str, object], schema: Mapping[str, object], path: str
) -> None:
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(
        isinstance(name, str) for name in required
    ):
        raise TypeError("schema required must be a list of strings")
    for name in required:
        if name not in payload:
            _fail(path, f"missing required property '{name}'")

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise TypeError("schema properties must be an object")
    if schema.get("additionalProperties") is False:
        unexpected = set(payload) - set(properties)
        if unexpected:
            _fail(path, f"unexpected property '{sorted(unexpected)[0]}'")
    for name, value in payload.items():
        property_schema = properties.get(name)
        if property_schema is None:
            continue
        if not isinstance(property_schema, Mapping):
            raise TypeError(f"schema for property '{name}' must be an object")
        _validate(value, property_schema, f"{path}.{name}")


def _validate_array(
    payload: list[object], schema: Mapping[str, object], path: str
) -> None:
    item_schema = schema.get("items")
    if item_schema is None:
        return
    if not isinstance(item_schema, Mapping):
        raise TypeError("schema items must be an object")
    for index, item in enumerate(payload):
        _validate(item, item_schema, f"{path}[{index}]")


def _validate_string(payload: str, schema: Mapping[str, object], path: str) -> None:
    minimum = schema.get("minLength")
    maximum = schema.get("maxLength")
    if minimum is not None and (not isinstance(minimum, int) or len(payload) < minimum):
        _fail(path, f"string must be at least {minimum} characters")
    if maximum is not None and (not isinstance(maximum, int) or len(payload) > maximum):
        _fail(path, f"string must be at most {maximum} characters")


def _unsupported_type(expected_type: str) -> bool:
    raise TypeError(f"unsupported schema type: {expected_type}")


def _fail(path: str, message: str) -> None:
    raise ValidationError(
        ErrorInfo(
            code="schema_validation_failed",
            message=f"{path}: {message}",
            retriable=False,
            failure_step="validation",
        )
    )
