"""Deterministic retry support for transient provider and transport failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from app.exceptions import ApplicationError, ErrorInfo, RetryExhaustedError

ResultType = TypeVar("ResultType")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configurable exponential-backoff settings for one operation."""

    max_retries: int = 3
    base_delay_seconds: float = 5.0
    multiplier: float = 3.0

    def __post_init__(self) -> None:
        """Reject invalid policy values before an operation executes."""

        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds cannot be negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")

    def delay_for_retry(self, retry_number: int) -> float:
        """Return delay for a one-indexed retry number."""

        if retry_number < 1:
            raise ValueError("retry_number must be at least 1")
        return self.base_delay_seconds * self.multiplier ** (retry_number - 1)


class RetryManager:
    """Retry only classified transient failures with exponential backoff."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """Create a retry manager with an injectable sleep function for tests."""

        self._policy = policy or RetryPolicy()
        self._sleep = sleep or _default_sleep

    def run(self, operation: Callable[[], ResultType]) -> ResultType:
        """Run an operation and retry only transient errors within the policy."""

        retries = 0
        while True:
            try:
                return operation()
            except Exception as error:
                if not self._is_transient(error):
                    raise
                if retries >= self._policy.max_retries:
                    raise RetryExhaustedError(
                        ErrorInfo(
                            code="retry_exhausted",
                            message=(
                                "The operation exhausted its transient retry budget."
                            ),
                            retriable=False,
                            failure_step="retry",
                        )
                    ) from error
                retries += 1
                self._sleep(self._policy.delay_for_retry(retries))

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        if isinstance(error, ApplicationError):
            return error.error.retriable
        return isinstance(error, (ConnectionError, TimeoutError))


def _default_sleep(delay_seconds: float) -> None:
    """Import sleep lazily so tests never wait during module import."""

    from time import sleep

    sleep(delay_seconds)
