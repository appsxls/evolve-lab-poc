"""Backend-independent contract for development execution."""
from typing import Protocol, TypedDict


class AgentStatus(TypedDict):
    name: str
    configured: bool
    message: str


class AgentNotConfiguredError(RuntimeError):
    """Raised when an agent cannot execute without further configuration."""


class Agent(Protocol):
    def status(self) -> AgentStatus:
        """Return readiness without contacting an external service."""
        ...

    def execute(self, request: str) -> None:
        """Execute a request or raise on failure.

        Phase one has no successful result contract. Future adapters must define
        validated artifacts and review semantics before enabling successful jobs.
        """
        ...
