"""Tests for provider-neutral priority routing using in-memory mocks only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.exceptions import ProviderUnavailableError, QuotaExceededError
from app.providers.base import ProviderHealth
from app.providers.router import ProviderRouter
from app.utils.retry import RetryManager, RetryPolicy


@dataclass
class MockProvider:
    """A test-only provider that performs no external work."""

    name: str
    priority: int
    available: bool = True
    calls: int = field(default=0, init=False)

    def health_check(self) -> ProviderHealth:
        """Return a deterministic health signal."""

        return ProviderHealth(available=self.available, checked_at=datetime.now(UTC))


def provider_error(
    error_type: type[ProviderUnavailableError],
) -> ProviderUnavailableError:
    """Build a transient provider error for mock operations."""

    return error_type.from_message(
        code="mock_provider_failure",
        message="Mock provider failed.",
        retriable=True,
        failure_step="mock",
    )


def test_router_selects_the_highest_priority_available_provider() -> None:
    """Configured priority, not input order, determines the primary provider."""

    secondary = MockProvider("secondary", priority=2)
    primary = MockProvider("primary", priority=1)

    router = ProviderRouter([secondary, primary])

    assert router.select() is primary
    assert router.available_providers() == (primary, secondary)


def test_router_skips_unavailable_provider_and_falls_back_after_quota_error() -> None:
    """Unavailable and quota-exhausted mocks lead to the next allowed provider."""

    unavailable = MockProvider("unavailable", priority=1, available=False)
    exhausted = MockProvider("exhausted", priority=2)
    fallback = MockProvider("fallback", priority=3)
    router = ProviderRouter([unavailable, exhausted, fallback])

    def operation(provider: MockProvider) -> str:
        provider.calls += 1
        if provider is exhausted:
            raise QuotaExceededError.from_message(
                code="quota_exhausted",
                message="Mock quota exhausted.",
                retriable=False,
                failure_step="mock",
            )
        return f"completed:{provider.name}"

    result = router.execute(operation)

    assert result.provider_name == "fallback"
    assert result.value == "completed:fallback"
    assert exhausted.calls == 1
    assert fallback.calls == 1
    assert unavailable.calls == 0


def test_router_can_disable_fallback() -> None:
    """Primary provider failure is surfaced when fallback policy is disabled."""

    router = ProviderRouter(
        [MockProvider("primary", priority=1), MockProvider("fallback", priority=2)],
        fallback_allowed=False,
    )

    def failed_operation(_provider: MockProvider) -> str:
        raise provider_error(ProviderUnavailableError)

    with pytest.raises(ProviderUnavailableError):
        router.execute(failed_operation)


def test_router_retries_transient_operation_before_returning_result() -> None:
    """A retry manager is applied to an operation before provider fallback."""

    attempts = 0
    delays: list[float] = []
    router = ProviderRouter(
        [MockProvider("primary", priority=1)],
        retry_manager=RetryManager(
            RetryPolicy(max_retries=1, base_delay_seconds=0), sleep=delays.append
        ),
    )

    def operation(_provider: MockProvider) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise provider_error(ProviderUnavailableError)
        return "recovered"

    assert router.execute(operation).value == "recovered"
    assert attempts == 2
    assert delays == [0]


def test_router_rejects_invalid_provider_configuration() -> None:
    """Empty and duplicate provider lists fail during setup."""

    with pytest.raises(ValueError, match="at least one"):
        ProviderRouter([])
    with pytest.raises(ValueError, match="unique"):
        ProviderRouter([MockProvider("same", 1), MockProvider("same", 2)])


def test_router_reports_when_no_provider_is_available() -> None:
    """A healthy provider is required before the operation is called."""

    router = ProviderRouter([MockProvider("offline", priority=1, available=False)])

    with pytest.raises(ProviderUnavailableError, match="No configured provider"):
        router.execute(lambda _provider: "not reached")
