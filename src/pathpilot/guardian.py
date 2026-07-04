"""Guardian: pre/post-tool hooks enforcing all safety guardrails (CLAUDE.md §2)."""
import json
import re
from typing import Any, Optional

from google.adk.tools import LongRunningFunctionTool

from .logger import slog

# ── constants ──────────────────────────────────────────────────────────────────

# External tools that take real-world actions — blocked until human approves (guardrail 1)
_EXTERNAL_TOOLS: frozenset[str] = frozenset(
    {"send_email", "submit_form", "post_message", "http_post", "http_put", "http_patch"}
)

# PII field names that must never leave the system in tool args or logs (guardrail 3)
_PII_FIELDS: frozenset[str] = frozenset({
    "name", "email", "phone", "address", "ssn",
    "passport_number", "visa_number", "transcript", "dob",
})

# Profile fields agents are permitted to use for task purposes (guardrail 3)
_MINIMUM_TASK_FIELDS: frozenset[str] = frozenset(
    {"visa", "gpa", "graduation", "field", "level"}
)

# Prompt-injection signatures to redact from tool output (guardrail 4, case-insensitive)
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore your",
    "ignore all previous",
    "disregard your",
    "forget your",
    "override your",
    "reveal the user",
    "reveal user data",
    "output the applicant",
    "administrative override",
    "new instructions:",
    "system:",
    "bypass",
)


# ── helpers (importable by tests) ──────────────────────────────────────────────

def minimum_profile_fields(profile: dict[str, Any]) -> set[str]:
    """Return only the non-PII task fields present in profile (guardrail 3)."""
    return set(profile.keys()) & _MINIMUM_TASK_FIELDS


def is_injection_attempt(text: str) -> bool:
    """Return True if text contains a known prompt-injection signature (guardrail 4)."""
    lower = text.lower()
    return any(p in lower for p in _INJECTION_PATTERNS)


def screen_tool_output(response: Any) -> Any:
    """Scan tool output for injection patterns and redact them (guardrail 4).

    The MCP server already excludes free-text description fields as a first line
    of defence.  This layer is defence-in-depth: it catches any pattern that
    reaches here via any future tool or field and ensures the LLM never sees a
    live instruction embedded in fetched data.

    Returns a sanitized copy; the original object is not mutated.
    """
    serialized = json.dumps(response) if not isinstance(response, str) else response
    if not is_injection_attempt(serialized):
        return response

    slog("warning", event="injection_attempt_in_tool_output")
    sanitized = serialized
    for pattern in _INJECTION_PATTERNS:
        sanitized = re.sub(
            re.escape(pattern),
            "[REDACTED:injection_attempt]",
            sanitized,
            flags=re.IGNORECASE,
        )
    try:
        return json.loads(sanitized)
    except (json.JSONDecodeError, ValueError):
        return {"_sanitized": True, "content": sanitized}


# ── human-in-the-loop approval tool ───────────────────────────────────────────

def request_send_approval(recipient: str, message: str) -> dict:
    """Human-in-the-loop gate for any outreach send (guardrail 1).

    Wrapped as a LongRunningFunctionTool so the ADK runner PAUSES immediately
    after this call and waits for the operator to resume with an explicit
    approval or rejection.  Nothing is transmitted here — this function only
    records the intent and returns a pending ticket for human review.
    """
    slog("info", event="send_approval_requested")
    return {
        "status": "pending",
        "recipient": recipient,
        "message": message,
        "approval_required": True,
        "note": (
            "This message has NOT been sent. "
            "Please review the recipient and message, then explicitly approve or reject."
        ),
    }


# Wrapped tool — the LongRunningFunctionTool causes ADK runner to pause on first
# return and only continue when the client resumes with an approval response.
send_approval_tool = LongRunningFunctionTool(func=request_send_approval)


# ── ADK callbacks ──────────────────────────────────────────────────────────────

def guardian_before_tool(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
) -> Optional[dict[str, Any]]:
    """Before-tool callback: blocks external actions and catches PII in args."""
    tool_name: str = getattr(tool, "name", str(tool))

    # Log the call without raw args — they may contain PII (guardrail 3)
    slog("info", event="tool_call", tool=tool_name)

    # Guardrail 1 — HUMAN-IN-THE-LOOP: block external real-world actions
    if tool_name in _EXTERNAL_TOOLS:
        slog("warning", event="guardian_blocked", tool=tool_name, reason="human_approval_required")
        return {
            "status": "blocked",
            "message": (
                f"Action '{tool_name}' requires explicit human approval in this session. "
                "Please confirm the exact action before it is taken."
            ),
        }

    # Guardrail 3 — PII STAYS LOCAL: block any call whose args include PII field names
    if args:
        pii_keys = [k for k in args if k.lower() in _PII_FIELDS]
        if pii_keys:
            slog("warning", event="pii_blocked", tool=tool_name, fields=pii_keys)
            return {
                "status": "blocked",
                "message": (
                    f"Tool call '{tool_name}' contained personal-data fields "
                    f"({pii_keys}) that must not be sent externally."
                ),
            }

    return None


def guardian_after_tool(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
) -> Any:
    """After-tool callback: screen tool output for prompt-injection content (guardrail 4)."""
    screened = screen_tool_output(tool_response)
    if screened is not tool_response:
        slog("warning", event="injection_sanitized", tool=getattr(tool, "name", str(tool)))
    return screened
