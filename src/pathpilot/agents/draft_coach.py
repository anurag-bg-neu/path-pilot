"""Draft Coach agent: honest HR outreach and cover-letter drafting using only user-provided facts."""
import os
import pathlib
from typing import Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from ..guardian import guardian_before_tool, send_approval_tool
from ..logger import slog

_MODEL = os.getenv("PATHPILOT_MODEL", "gemini-3.1-flash-lite")

_SKILL_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "skills"
    / "draft-coaching"
    / "SKILL.md"
)
_SKILL_INSTRUCTION = _SKILL_PATH.read_text(encoding="utf-8")

_INSTRUCTION = (
    _SKILL_INSTRUCTION
    + """
SENDING RULE (guardrail 1, HUMAN-IN-THE-LOOP):
- NEVER send or transmit any message directly.
- When the student asks to send an outreach message, call the function named exactly
  `request_send_approval`; call it bare, with no agent-name prefix and no namespace
  (NOT `draft_coach.request_send_approval`, NOT `functions.request_send_approval`).
  It is the only sending-related tool available to you. Pass the recipient and message
  text as its arguments. This pauses for explicit human approval.
- Do not proceed until the human has confirmed approval in this session.
- After approval, tell the student: "Your approval has been recorded. The message has
  NOT been sent yet; a human operator must action the approved request." Never say
  the message was sent or submitted for sending.
"""
)

# Markers that signal fabricated content; must never appear unless the student stated them.
_FABRICATION_MARKERS: frozenset[str] = frozenset(
    {"award", "prize", "medal", "ceo", "co-founded", "co-founder", "patent"}
)

# Request phrases that hint the user wants embellishment; we refuse and ask for real facts.
_FABRICATION_TRIGGERS: tuple[str, ...] = (
    "more impressive",
    "sound impressive",
    "exaggerate",
    "embellish",
    "make me look",
    "add something",
    "invent",
    "make up",
)

# The only bare tool names this agent can actually dispatch. Gemini occasionally
# hallucinates an agent-qualified variant (e.g. "draft_coach.request_send_approval")
# instead of the bare registered name, which ADK's tool lookup does not understand
# and raises a hard ValueError for, crashing the run. Prompt wording alone cannot
# guarantee this never happens, so we also sanitize it in code (guardrail 1).
_KNOWN_TOOL_NAMES: frozenset[str] = frozenset({"request_send_approval"})


def _degrade_qualified_tool_name(name: str) -> str:
    """Strip any agent/namespace prefix from a hallucinated qualified tool name."""
    if name in _KNOWN_TOOL_NAMES:
        return name
    bare = name.rsplit(".", 1)[-1]
    return bare if bare in _KNOWN_TOOL_NAMES else name


# ── pure-Python drafting function (used directly in tests) ───────────────────

def draft_essay(facts: dict, request: str = "") -> dict:
    """Draft an essay/message using ONLY the supplied facts (guardrail 2).

    Never invents credentials, awards, or experiences. If the request implies
    embellishment, notes what additional real facts would strengthen the draft.
    Returns ``{"draft": str, "changes": list[str]}``.
    """
    experience = facts.get("experience", "")
    skills = facts.get("skills", [])
    skills_text = ", ".join(skills) if isinstance(skills, list) else str(skills)

    sentences: list[str] = []
    if experience:
        sentences.append(f"I have experience as {experience}")
    if skills_text:
        sentences.append(f"My technical skills include {skills_text}")

    draft = ". ".join(sentences) + ("." if sentences else "")
    if not draft.strip():
        draft = (
            "I would be happy to help; please share your experiences and skills "
            "so I can draft your essay without inventing any content."
        )

    changes: list[str] = ["Built draft exclusively from provided facts"]
    if skills_text:
        changes.append(f"Highlighted stated skills: {skills_text}")

    needs_fabrication = any(t in request.lower() for t in _FABRICATION_TRIGGERS)
    if needs_fabrication:
        changes.append(
            "Embellishment request noted but not fulfilled (guardrail 2: NO FABRICATION). "
            "To strengthen the draft, please share specific achievements, metrics, or "
            "project outcomes; nothing will be invented."
        )

    return {"draft": draft, "changes": changes}


# ── after_model_callback: log if the LLM sneaks in fabricated markers ────────

def fabrication_guard(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Audit log when model output contains fabrication markers (guardrail 2),
    and sanitize any hallucinated agent-qualified tool-call name (guardrail 1).

    Hard-blocking by word match causes false positives when the student has
    explicitly confirmed a fact mid-conversation (e.g. "yes I really won the
    NSF award").  The instruction layer in SKILL.md handles the nuanced
    confirmation flow; this callback is the audit trail that surfaces
    unexpected fabrication for operator review.
    """
    text = ""
    try:
        if llm_response.content and llm_response.content.parts:
            for part in llm_response.content.parts:
                if hasattr(part, "text") and part.text:
                    text += part.text + " "

                function_call = getattr(part, "function_call", None)
                if function_call is not None and function_call.name:
                    corrected = _degrade_qualified_tool_name(function_call.name)
                    if corrected != function_call.name:
                        slog(
                            "warning",
                            event="tool_name_hallucination_corrected",
                            original=function_call.name,
                            corrected=corrected,
                        )
                        function_call.name = corrected
    except Exception:
        pass

    found = [m for m in _FABRICATION_MARKERS if m in text.lower()]
    if found:
        slog("warning", event="fabrication_marker_in_model_output", markers=found)

    return None  # pass through; instruction layer owns the blocking decision


# ── agent ──────────────────────────────────────────────────────────────────────

draft_coach_agent = LlmAgent(
    name="draft_coach",
    model=_MODEL,
    description=(
        "Drafts honest HR outreach emails and cover letters using only the user-supplied "
        "facts or the RESUME PROFILE block. Auto-drafts emails for top 3 matched jobs "
        "after eligibility ranking (Mode B)."
    ),
    instruction=_INSTRUCTION,
    tools=[send_approval_tool],
    before_tool_callback=guardian_before_tool,
    after_model_callback=fabrication_guard,
)
