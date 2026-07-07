"""Guardian: pre/post-tool hooks enforcing all safety guardrails (AGENTS.md §2)."""
import json
import re
from typing import Any, Optional

from google.adk.models.llm_response import LlmResponse
from google.adk.tools import LongRunningFunctionTool
from google.genai import types as genai_types

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

# Literal marker eligibility emits (see skills/eligibility-checking/SKILL.md Mode B,
# Step 0) when it needs the job seeker to confirm their work-authorization status
# in chat before scoring citizenship/clearance-restricted roles. This is never
# resume-derived — resume_parser never emits it — only ever follows a plain-text
# statement the user typed themselves (guardrail 3).
WORK_AUTH_PENDING_MARKER = "<!-- PATHPILOT_WORK_AUTH_PENDING -->"

# Keywords that plausibly answer the work-authorization confirmation question.
# Deterministic safety valve: only force-route to eligibility when the reply
# actually looks like an answer, so a genuine topic change (e.g. "show me
# scholarships instead") still falls through to normal LLM routing.
_WORK_AUTH_ANSWER_KEYWORDS: tuple[str, ...] = (
    "citizen", "green card", "greencard", "permanent resident",
    "visa", "sponsor", "opt", "cpt", "clearance",
    "h-1b", "h1b", "f-1", "f1", "prefer not",
)

# Session-state key eligibility sets when it asks the work-auth confirmation
# question (see eligibility.py's ensure_work_auth_marker). Session state is
# used instead of scanning conversation text because ADK scopes a request's
# `contents` to the current invocation branch: once eligibility (a sub-agent
# nested under resume_then_score) hands control back to the root orchestrator,
# the root's own next before_model_callback cannot see eligibility's message —
# it's on a deeper branch. State has no such scoping, so it's the only
# reliable way to carry this signal back across the branch boundary.
WORK_AUTH_PENDING_STATE_KEY = "work_auth_pending"


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


# ── work-authorization confirmation routing ───────────────────────────────────

def _content_text(content: Any) -> str:
    """Flatten a genai Content's text parts into one lowercase string."""
    if not content or not getattr(content, "parts", None):
        return ""
    return " ".join(
        p.text for p in content.parts if getattr(p, "text", None)
    ).lower()


def route_work_auth_confirmation_reply(
    callback_context: Any,
    llm_request: Any,
) -> Optional[LlmResponse]:
    """Deterministically route a work-auth confirmation reply to eligibility.

    The orchestrator's LLM routing has a known failure mode with this model
    (see agent.py's comment on resume_then_score being hardwired because
    gemini-flash-lite "kept ignoring" fragile instruction-based routing) —
    trusting it to correctly classify "does this reply answer the pending
    work-auth question" would reintroduce that same risk. Instead this checks
    both conditions in code: state carries the pending-question flag eligibility
    set (see WORK_AUTH_PENDING_STATE_KEY) AND this new user turn plausibly
    answers it (keyword match). If both hold, synthesize the
    transfer_to_agent(eligibility) call directly, bypassing the orchestrator's
    own LLM call for this turn entirely (deterministic, no hallucination
    risk). Otherwise return None and let normal LLM routing proceed, so a
    genuine topic change still routes normally instead of being force-fed to
    eligibility.
    """
    contents = getattr(llm_request, "contents", None) or []
    if not contents:
        return None

    last_content = contents[-1]
    if getattr(last_content, "role", None) != "user":
        return None

    state = getattr(callback_context, "state", None)
    if state is None or not state.get(WORK_AUTH_PENDING_STATE_KEY):
        return None

    user_text = _content_text(last_content)
    if not any(k in user_text for k in _WORK_AUTH_ANSWER_KEYWORDS):
        return None

    # Consume the flag so a later, unrelated turn that happens to mention one
    # of these keywords (e.g. "what about visa sponsorship in general?") isn't
    # force-routed to eligibility again.
    state[WORK_AUTH_PENDING_STATE_KEY] = False

    slog("info", event="work_auth_reply_routed", target="eligibility")
    return LlmResponse(
        content=genai_types.Content(
            role="model",
            parts=[
                genai_types.Part(
                    function_call=genai_types.FunctionCall(
                        name="transfer_to_agent",
                        args={"agent_name": "eligibility"},
                    )
                )
            ],
        )
    )


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

    # Guardrail — ELIGIBILITY IS ANALYSIS-ONLY: block any tool call from the eligibility agent.
    # eligibility has tools=[] so ADK prevents most calls, but this callback is the hard stop
    # that ensures the run continues gracefully rather than crashing.
    agent_name: str = getattr(tool_context, "agent_name", None) or ""
    if agent_name == "eligibility":
        slog("warning", event="guardian_blocked", tool=tool_name, reason="eligibility_analysis_only")
        return {
            "status": "blocked",
            "message": "Eligibility agent is analysis-only. No tool calls are permitted from this agent.",
        }

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
