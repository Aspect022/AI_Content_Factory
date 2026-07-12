"""Priority-aware provider routing with availability checks and fallback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.exceptions import ProviderError, ProviderUnavailableError, RetryExhaustedError
from app.providers.base import Provider
from app.utils.retry import RetryManager

ProviderType = TypeVar("ProviderType", bound=Provider)
ResultType = TypeVar("ResultType")


@dataclass(frozen=True, slots=True)
class RouterResult(Generic[ResultType]):
    """Successful result returned through a selected provider."""

    provider_name: str
    value: ResultType


class ProviderRouter(Generic[ProviderType]):
    """Select providers by priority and fail forward when allowed."""

    def __init__(
        self,
        providers: Iterable[ProviderType],
        *,
        fallback_allowed: bool = True,
        retry_manager: RetryManager | None = None,
    ) -> None:
        """Create a router with unique providers ordered by ascending priority."""

        ordered = tuple(sorted(providers, key=lambda provider: provider.priority))
        if not ordered:
            raise ValueError("ProviderRouter requires at least one provider")
        names = [provider.name for provider in ordered]
        if len(names) != len(set(names)):
            raise ValueError("ProviderRouter provider names must be unique")

        self._providers = ordered
        self._fallback_allowed = fallback_allowed
        self._retry_manager = retry_manager

    def available_providers(self) -> tuple[ProviderType, ...]:
        """Return healthy providers in configured priority order."""

        return tuple(
            provider
            for provider in self._providers
            if provider.health_check().available
        )

    def select(self) -> ProviderType:
        """Return the highest-priority available provider."""

        available = self.available_providers()
        if not available:
            raise ProviderUnavailableError.from_message(
                code="no_provider_available",
                message="No configured provider is currently available.",
                retriable=True,
                failure_step="provider_routing",
            )
        return available[0]

    def execute(
        self, operation: Callable[[ProviderType], ResultType]
    ) -> RouterResult[ResultType]:
        """Execute through the preferred provider, falling back when permitted."""

        available = self.available_providers()
        if not available:
            self.select()

        last_error: ProviderError | None = None
        for index, provider in enumerate(available):
            try:
                value = self._run_operation(operation, provider)
            except ProviderError as error:
                last_error = error
                if not self._fallback_allowed or index == len(available) - 1:
                    raise
            except RetryExhaustedError as error:
                last_provider_error = error.__cause__
                if not isinstance(last_provider_error, ProviderError):
                    raise
                last_error = last_provider_error
                if not self._fallback_allowed or index == len(available) - 1:
                    raise last_provider_error from error
            else:
                return RouterResult(provider_name=provider.name, value=value)

        if last_error is not None:
            raise last_error
        raise AssertionError("The provider router reached an unreachable state")

    def _run_operation(
        self,
        operation: Callable[[ProviderType], ResultType],
        provider: ProviderType,
    ) -> ResultType:
        if self._retry_manager is None:
            return operation(provider)
        return self._retry_manager.run(lambda: operation(provider))
