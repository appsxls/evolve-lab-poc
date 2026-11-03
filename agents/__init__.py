"""Development agent adapter contract and default implementation."""
from .base import Agent, AgentNotConfiguredError
from .cloud import CloudAgent

__all__ = ['Agent', 'AgentNotConfiguredError', 'CloudAgent']
