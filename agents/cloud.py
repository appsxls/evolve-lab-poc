"""Cloud placeholder: no SDK, credentials, network calls, or local fallback."""
from .base import AgentNotConfiguredError, AgentStatus


class CloudAgent:
    MESSAGE = 'Cloud agent is not configured. Development execution is unavailable in this phase.'

    def status(self) -> AgentStatus:
        return {'name': 'cloud', 'configured': False, 'message': self.MESSAGE}

    def execute(self, request: str) -> None:
        raise AgentNotConfiguredError(self.MESSAGE)
