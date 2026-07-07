"""AuditLogPlugin: structured, PII-free logging for every agent turn and tool call."""
from typing import Any, Optional

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.runners import InvocationContext
from google.adk.tools.base_tool import BaseTool

from .logger import slog

# PII field names — never log values of these keys, even from tool args (guardrail 3)
_PII_FIELDS: frozenset[str] = frozenset({
    "name", "email", "phone", "address", "ssn",
    "passport_number", "visa_number", "transcript", "dob",
})


def _safe_arg_keys(tool_args: dict[str, Any]) -> list[str]:
    """Return only the argument *names* (never values) minus any PII keys."""
    return [k for k in tool_args if k.lower() not in _PII_FIELDS]


class AuditLogPlugin(BasePlugin):
    """Emit a structured JSON audit-log entry at every significant lifecycle point.

    Covers (AGENTS.md §2 guardrail 7 — OBSERVABILITY):
    - Invocation start/end
    - Agent turn start/end
    - Tool call start/end  (arg *names* only — never values)
    - Model error
    - Tool error
    """

    def __init__(self) -> None:
        super().__init__(name="pathpilot_audit_log")

    # ── invocation boundary ───────────────────────────────────────────────────

    async def before_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        slog(
            "info",
            event="invocation_start",
            invocation_id=invocation_context.invocation_id,
            agent=invocation_context.agent.name,
        )

    async def after_run_callback(
        self, *, invocation_context: InvocationContext
    ) -> None:
        slog(
            "info",
            event="invocation_end",
            invocation_id=invocation_context.invocation_id,
        )

    # ── agent turn boundary ───────────────────────────────────────────────────

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> Optional[Any]:
        slog("info", event="agent_turn_start", agent=agent.name)
        return None

    async def after_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> Optional[Any]:
        slog("info", event="agent_turn_end", agent=agent.name)
        return None

    # ── tool call boundary ────────────────────────────────────────────────────

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: Any,
    ) -> Optional[dict]:
        slog(
            "info",
            event="tool_call_start",
            tool=tool.name,
            agent=tool_context.agent_name,
            arg_keys=_safe_arg_keys(tool_args),
        )
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict,
    ) -> Optional[dict]:
        slog(
            "info",
            event="tool_call_end",
            tool=tool.name,
            agent=tool_context.agent_name,
        )
        return None

    # ── error hooks ───────────────────────────────────────────────────────────

    async def on_model_error_callback(
        self,
        *,
        callback_context: CallbackContext,
        llm_request: LlmRequest,
        error: Exception,
    ) -> Optional[LlmResponse]:
        slog("error", event="model_error", error=type(error).__name__, detail=str(error)[:200])
        return None

    async def on_tool_error_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: Any,
        error: Exception,
    ) -> Optional[dict]:
        slog(
            "error",
            event="tool_error",
            tool=tool.name,
            error=type(error).__name__,
            detail=str(error)[:200],
        )
        return None
