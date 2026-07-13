"""Tests for environment-only configuration loading."""

from pathlib import Path

import pytest

from app.config import load_config
from app.exceptions import ConfigurationError


def test_load_config_returns_redacted_safe_summary(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Valid configuration is loaded while secret values stay out of summaries."""

    configuration = load_config(required_environment, project_root)

    assert configuration.data_directory == project_root / "data"
    assert configuration.default_language == "hi"
    assert configuration.default_provider_policy == "fallback_allowed"
    assert configuration.video_duration_seconds == 8
    assert [profile.name for profile in configuration.video_provider_profiles] == [
        "flow_quality",
        "openrouter",
        "flow_fallback",
    ]
    assert configuration.video_provider_profiles[1].model == "alibaba/wan-2.6:free"
    assert "test-groq-key" not in str(configuration.redacted_summary())
    assert configuration.redacted_summary()["qwen_configured"] is False


def test_load_config_reports_all_missing_variables(project_root: Path) -> None:
    """Missing secrets fail early with structured, non-secret error details."""

    with pytest.raises(ConfigurationError) as raised:
        load_config({}, project_root)

    assert raised.value.error.code == "missing_required_configuration"
    assert "GEMINI_FALLBACK_API_KEY" in raised.value.error.message


def test_load_config_does_not_require_a_personal_github_token(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """GitHub Actions supplies its built-in token only to the workflow itself."""

    required_environment.pop("GITHUB_TOKEN", None)

    configuration = load_config(required_environment, project_root)

    assert configuration.run_timezone == "Asia/Kolkata"


def test_load_config_rejects_an_invalid_timezone(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """The engineering-specified runtime timezone is enforced."""

    required_environment["RUN_TIMEZONE"] = "UTC"

    with pytest.raises(ConfigurationError) as raised:
        load_config(required_environment, project_root)

    assert raised.value.error.code == "invalid_run_timezone"


def test_load_config_rejects_an_invalid_provider_policy(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Provider policy is limited to the documented values."""

    required_environment["DEFAULT_PROVIDER_POLICY"] = "all_at_once"

    with pytest.raises(ConfigurationError) as raised:
        load_config(required_environment, project_root)

    assert raised.value.error.code == "invalid_provider_policy"


def test_load_config_rejects_unsupported_single_clip_duration(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Version 1 permits only the supported single-clip video durations."""

    required_environment["VIDEO_DURATION_SECONDS"] = "15"

    with pytest.raises(ConfigurationError) as raised:
        load_config(required_environment, project_root)

    assert raised.value.error.code == "invalid_video_duration"


def test_load_config_allows_single_text_provider_key(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Any one configured text provider should satisfy text runtime validation."""

    required_environment["NVIDIA_API_KEY"] = ""
    required_environment["GEMINI_API_KEY"] = ""

    configuration = load_config(required_environment, project_root)

    assert configuration.groq_api_key == "test-groq-key"
    assert configuration.nvidia_api_key is None
    assert configuration.gemini_api_key is None


def test_load_config_requires_at_least_one_text_provider_key(
    required_environment: dict[str, str], project_root: Path
) -> None:
    """Runtime configuration fails when no text provider credential is supplied."""

    required_environment["GROQ_API_KEY"] = ""
    required_environment["NVIDIA_API_KEY"] = ""
    required_environment["GEMINI_API_KEY"] = ""

    with pytest.raises(ConfigurationError) as raised:
        load_config(required_environment, project_root)

    assert raised.value.error.code == "missing_text_provider_configuration"
