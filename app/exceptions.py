"""Typed exceptions shared across the application."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """Machine-readable information describing an application failure."""

    code: str
    message: str
    retriable: bool
    failure_step: str | None = None

    def to_dict(self) -> dict[str, bool | str | None]:
        """Return a JSON-serializable representation of the error."""

        return {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "failure_step": self.failure_step,
        }


class ApplicationError(Exception):
    """Base class for expected, structured application failures."""

    def __init__(self, error: ErrorInfo) -> None:
        """Create an exception from structured failure information."""

        super().__init__(error.message)
        self.error = error

    @classmethod
    def from_message(
        cls,
        *,
        code: str,
        message: str,
        retriable: bool,
        failure_step: str | None = None,
    ) -> ApplicationError:
        """Construct a typed error from its durable error fields."""

        return cls(
            ErrorInfo(
                code=code,
                message=message,
                retriable=retriable,
                failure_step=failure_step,
            )
        )


class ConfigurationError(ApplicationError):
    """Raised when required runtime configuration is missing or invalid."""


class ValidationError(ApplicationError):
    """Raised when a structured payload does not satisfy its contract."""


class ProviderError(ApplicationError):
    """Base class for failures raised by a provider abstraction."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider cannot serve the current request."""


class QuotaExceededError(ProviderError):
    """Raised when a provider has no permitted capacity for a request."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider rejects its configured credentials."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns malformed or contract-invalid output."""


class UploadError(ApplicationError):
    """Raised when an upload provider cannot complete an upload."""


class NotificationError(ApplicationError):
    """Raised when a notification provider cannot deliver a message."""


class RetryExhaustedError(ApplicationError):
    """Raised after the retry policy exhausts all permitted attempts."""
