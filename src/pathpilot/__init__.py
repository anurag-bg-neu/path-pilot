"""PathPilot package — exposes app (with AuditLogPlugin) for `adk web`."""
from .agent import app, root_agent

__all__ = ["app", "root_agent"]
