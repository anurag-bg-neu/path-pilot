"""Eligibility agent: judges opportunities against the job seeker's profile."""
import os
import pathlib
from typing import Any, Optional

from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_response import LlmResponse

from ..guardian import (
    WORK_AUTH_PENDING_MARKER,
    WORK_AUTH_PENDING_STATE_KEY,
    guardian_before_tool,
)

_MODEL = os.getenv("PATHPILOT_MODEL", "gemini-3.1-flash-lite")

_SKILL_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "skills" / "eligibility-checking" / "SKILL.md"
)
_INSTRUCTION = _SKILL_PATH.read_text(encoding="utf-8") + """
TOOL RULE: CRITICAL (crashes the app if broken, so NEVER break it):
- You have ZERO callable tools. Do NOT generate any function call whatsoever.
- This includes ALL names: resume_parser, resume_parsing, parse_resume, extract_resume,
  search, fetch, lookup, google_search, or any other function name.
- Any function call you generate will be intercepted by the guardian and blocked; the run
  will NOT proceed past that point.
- If a PDF file is visible in the conversation WITHOUT a "RESUME PROFILE" block already
  present, do NOT try to parse it. Instead output exactly:
  "I need a structured RESUME PROFILE before I can score jobs. Please ask the
   orchestrator to run Resume Parser on your uploaded file first."
  Then stop. Do not attempt to call anything.
- The RESUME PROFILE is always extracted by the Resume Parser agent BEFORE you are
  called. It appears as a "RESUME PROFILE (PII-free):" block in the conversation.
  If it is not there yet, that block is missing; say so and stop.
- You can ONLY evaluate opportunities already described in the conversation context.
- Never fetch job descriptions, never search; that is Discovery's job.

OUTPUT FORMAT RULES (Mode B, never break):
- FIRST, apply Step 0 from the skill (work-authorization confirmation gate). If Step 0
  says to ask the confirmation question, your ENTIRE response is that question plus the
  literal `<!-- PATHPILOT_WORK_AUTH_PENDING -->` line; do NOT also output the heading
  or table below in that same turn.
- Otherwise (Step 0 was skipped, or a status is already confirmed), continue below.
- NEVER output the RESUME PROFILE block or any summary of the job seeker's profile.
  The profile is a private internal artifact. Your response must start directly with
  the heading below; nothing before it.
- Your response MUST begin with this exact heading on its own line:
  ## 🎯 Curated matches ranked for your profile
- Score ALL available jobs, then rank them by score descending.
- Output EVERY job Discovery scraped this session in a SINGLE markdown table: no cap,
  no "top N", no pagination. If 97 jobs are in context, the table has 97 rows.
- After the heading, output a strict markdown table: no other prose before the table.
- The table MUST have exactly these 8 columns in this order:
  | # | Job Title | Company | 🎯 Score | 💰 Salary | 📅 Posted | ✅ Skills | Apply |
- 🎯 Score MUST be a number out of 100, e.g. "87/100". Never write text like "Strong".
- 💰 Salary: use the salary value from the job listing (e.g. "USD 120k–150k/yr").
  If not available write "-".
- 📅 Posted: use the posted_at date from the job listing (e.g. "2026-06-30").
  If not available write "-".
- ✅ Skills: comma-separated matched skills, e.g. "Python, AWS, SQL". If none: "-".
- Apply MUST be an HTML link: <a href="URL" target="_blank" rel="noopener">Apply</a>
  If no URL is available write "-".
- # column: use the absolute rank (1 = highest score, last = lowest in the table).

ROW-COUNT SELF-CHECK: CRITICAL (this exact failure has happened before, read twice):
- Before you respond, count the job objects available in context from Discovery's
  results (call this N). Score every single one of them; do not stop after 5, 10,
  or any other round number "for brevity". Scoring is per-job arithmetic, not deep
  research; it is not an excuse to shorten the table.
- Your table MUST have exactly N data rows. After drafting, count your own table
  rows and compare to N. If they disagree, you truncated the list; go back and add
  the missing rows before responding. Truncating without being asked is a bug, not
  a helpful simplification.
- Being off by even ONE row is the same bug, not a rounding error; a missing row
  is exactly as wrong as a missing 20. Two jobs with identical-looking title and
  company are NOT the same listing to merge into one row; Discovery already
  dedupes true duplicates by source URL before you ever see them, so if you still
  see two that look alike, they are two distinct postings and both get their own
  scored row.
- Do this recount twice: once right after drafting the table, and once more,
  literally, immediately before you send the response.
- NEVER replace missing rows with a note like "(Note: a full list of all N roles is
  available, let me know if you'd like to see the rest)"; that note is itself the
  bug this rule exists to prevent. There is no "rest to see later"; it all belongs
  in this one response, right now.

- DO NOT add "General Feedback", "Next Steps", "Top Recommendations", or any prose after the table.
"""

_TABLE_HEADING = "Curated matches"

# Phrases specific to the Step 0 confirmation question and nowhere else in this
# agent's vocabulary (not the "need a RESUME PROFILE" error, not the ranked
# table), used to recognize the question shape without relying on the model
# having remembered to also include the literal marker itself.
_CONFIRMATION_QUESTION_MARKERS: tuple[str, ...] = (
    "work authorization",
    "prefer not to say",
)


def ensure_work_auth_marker(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Guarantee WORK_AUTH_PENDING_MARKER is present whenever this response is
    the Step 0 confirmation question; never rely on the model alone to
    remember the literal marker line every time.

    Also sets WORK_AUTH_PENDING_STATE_KEY in session state, not just the
    in-text marker. ADK scopes a request's `contents` to the current
    invocation branch, so once this response hands control back to the root
    orchestrator, the root's own next before_model_callback cannot see this
    (nested sub-agent's) message to look for the in-text marker at all.
    Session state has no such scoping, so it is what
    ``guardian.route_work_auth_confirmation_reply`` actually keys off of; the
    in-text marker remains for the frontend's quick-reply-button detection,
    which reads the live SSE stream directly rather than reconstructed
    request contents.
    """
    if not llm_response.content or not llm_response.content.parts:
        return None

    text = " ".join(
        p.text for p in llm_response.content.parts if getattr(p, "text", None)
    )
    if not text or _TABLE_HEADING in text:
        return None  # final table, nothing to do

    if not any(m in text.lower() for m in _CONFIRMATION_QUESTION_MARKERS):
        return None  # not the confirmation question (e.g. the "need a RESUME PROFILE" error)

    callback_context.state[WORK_AUTH_PENDING_STATE_KEY] = True

    if WORK_AUTH_PENDING_MARKER in text:
        return None  # marker already present, nothing else to do

    for part in llm_response.content.parts:
        if getattr(part, "text", None):
            part.text = part.text + "\n" + WORK_AUTH_PENDING_MARKER
            return None
    return None


eligibility_agent = LlmAgent(
    name="eligibility",
    model=_MODEL,
    description="Judges each opportunity against the job seeker's profile (skills, eligibility, deadline).",
    instruction=_INSTRUCTION,
    tools=[],
    before_tool_callback=guardian_before_tool,
    after_model_callback=ensure_work_auth_marker,
)


_CITIZEN_STATUSES = frozenset({"citizen_or_green_card", "citizen", "green_card"})
_SPONSORSHIP_STATUSES = frozenset({"needs_sponsorship", "f1_opt_cpt", "visa"})
_UNKNOWN_STATUSES = frozenset({"", "prefer_not_to_say", "unknown"})


def evaluate_opportunity(opp: dict, work_auth: str = "") -> dict:
    """Deterministic rule-based eligibility check for a single opportunity.

    Handles both fixture field names (citizenship_required / clearance) and
    MCP seed-data field names (requires_citizenship / requires_clearance).

    ``work_auth`` is the job seeker's explicitly chat-confirmed status; never
    resume-derived (see skills/eligibility-checking/SKILL.md Mode B, Step 0):
    - "citizen_or_green_card": citizenship/clearance-required roles are Eligible.
    - "needs_sponsorship" (or an unrecognized specific value, e.g. a stated visa
      type): citizenship/clearance-required roles are Not eligible.
    - "" / "prefer_not_to_say" (not yet confirmed): citizenship/clearance-required
      roles are "Needs info"; never assumed ineligible by default.
    """
    needs_citizenship = opp.get("citizenship_required") or opp.get("requires_citizenship")
    needs_clearance = opp.get("clearance") or opp.get("requires_clearance")

    if needs_citizenship or needs_clearance:
        status = work_auth if work_auth in _CITIZEN_STATUSES | _UNKNOWN_STATUSES else "needs_sponsorship"
        if status in _CITIZEN_STATUSES:
            return {
                "verdict": "Eligible",
                "reason": "Requires US citizenship or a security clearance, which your confirmed status meets.",
            }
        if status in _UNKNOWN_STATUSES:
            return {
                "verdict": "Needs info",
                "reason": "Requires US citizenship or a security clearance; confirm your work-authorization status to resolve this.",
            }
        return {
            "verdict": "Not eligible",
            "reason": "Requires US citizenship or a security clearance that your confirmed status does not meet.",
        }

    cpt_ok = opp.get("cpt_opt_compatible")
    intl_ok = opp.get("open_to_international")

    reason = (
        "CPT/OPT work authorization accepted."
        if cpt_ok
        else "Open to international applicants; no citizenship or clearance restriction."
        if intl_ok
        else "No citizenship or clearance requirement; eligible under CPT/OPT work authorization."
    )
    return {"verdict": "Eligible", "reason": reason}
