from typing import Protocol

from camora.models import BaseTask, PayloadDict, TaskDict


class Broker(Protocol):
    """Broker interface."""

    async def check_health(self) -> None:
        """Check broker health.

        Raises:
            Exception: If broker is not healthy.
        """

    async def read(self) -> list[TaskDict]:
        """Read tasks from broker."""
        ...

    async def publish(self, payload: PayloadDict) -> None:
        """Publish task to broker."""

    async def handle_success(self, task: BaseTask) -> None:
        """Handle successful task execution."""

    async def handle_giveup(self, task: BaseTask, error: Exception) -> None:
        """Handle task execution failure, after using all retries."""


class Logger(Protocol):
    """Logger interface."""

    def info(self, mgs: str, *args, **kwargs) -> None:
        """Log info message."""

    def error(self, mgs: str, *args, **kwargs) -> None:
        """Log error message."""


class SilentLogger:
    """Placeholder implementation of the Logger interface.

    Used when no logger is provided to the app. Does nothing.
    """

    def info(self, mgs: str, *args, **kwargs) -> None:
        """Do nothing."""

    def error(self, mgs: str, *args, **kwargs) -> None:
        """Do nothing."""
