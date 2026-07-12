"""Tests for transient-only exponential retry behavior."""

from __future__ import annotations

import pytest

from app.exceptions import ValidationError
from app.utils.retry import RetryManager, RetryPolicy


def test_retry_manager_uses_configured_exponential_backoff() -> None:
    """Transient errors retry until the operation recovers."""

    attempts = 0
    delays: list[float] = []
    manager = RetryManager(
        RetryPolicy(max_retries=2, base_delay_seconds=2, multiplier=3),
        sleep=delays.append,
    )

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "complete"

    assert manager.run(operation) == "complete"
    assert delays == [2, 6]


def test_retry_manager_does_not_retry_non_transient_application_errors() -> None:
    """Structured permanent failures are immediately surfaced."""

    delays: list[float] = []
    manager = RetryManager(sleep=delays.append)

    with pytest.raises(ValidationError):
        manager.run(
            lambda: (_ for _ in ()).throw(
                ValidationError.from_message(
                    code="invalid_payload",
                    message="Permanent validation failure.",
                    retriable=False,
                )
            )
        )

    assert delays == []


def test_retry_manager_rejects_invalid_policy_values() -> None:
    """Retry configuration is validated before it can cause a bad loop."""

    with pytest.raises(ValueError, match="max_retries"):
        RetryPolicy(max_retries=-1)
    with pytest.raises(ValueError, match="base_delay"):
        RetryPolicy(base_delay_seconds=-1)
    with pytest.raises(ValueError, match="multiplier"):
        RetryPolicy(multiplier=0.5)
    with pytest.raises(ValueError, match="retry_number"):
        RetryPolicy().delay_for_retry(0)
