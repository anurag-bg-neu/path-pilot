"""Eligibility agent: judges opportunities against the student's profile."""
import os
import pathlib

from google.adk.agents import LlmAgent

from ..guardian import guardian_before_tool

_MODEL = os.getenv("PATHPILOT_MODEL", "gemini-3.1-flash-lite")

_SKILL_PATH = (
    pathlib.Path(__file__).parent.parent.parent.parent
    / "skills" / "eligibility-checking" / "SKILL.md"
)
_INSTRUCTION = _SKILL_PATH.read_text(encoding="utf-8") + """
TOOL RULE — CRITICAL (crashes the app if broken, so NEVER break it):
- You have ZERO callable tools. Do NOT generate any function call whatsoever.
- This includes ALL names: resume_parser, resume_parsing, parse_resume, extract_resume,
  search, fetch, lookup, google_search — or any other function name.
- Any function call you generate will be intercepted by the guardian and blocked; the run
  will NOT proceed past that point.
- If a PDF file is visible in the conversation WITHOUT a "RESUME PROFILE" block already
  present, do NOT try to parse it. Instead output exactly:
  "I need a structured RESUME PROFILE before I can score jobs. Please ask the
   orchestrator to run Resume Parser on your uploaded file first."
  Then stop — do not attempt to call anything.
- The RESUME PROFILE is always extracted by the Resume Parser agent BEFORE you are
  called. It appears as a "RESUME PROFILE (PII-free):" block in the conversation.
  If it is not there yet, that block is missing — say so and stop.
- You can ONLY evaluate opportunities already described in the conversation context.
- Never fetch job descriptions, never search — that is Discovery's job.

OUTPUT FORMAT RULES (Mode B — never break):
- NEVER output the RESUME PROFILE block or any summary of the student's profile.
  The profile is a private internal artifact. Your response must start directly with
  the heading below — nothing before it.
- Your response MUST begin with this exact heading on its own line:
  ## 🎯 Curated Matches — Ranked for Your Profile
- Score ALL available jobs, then rank them by score descending.
- Keep the top 50 ranked jobs internally. Display them PAGINATED, 10 rows per page.
- After the heading, output a strict markdown table — no other prose before the table.
- The table MUST have exactly these 8 columns in this order:
  | # | Job Title | Company | 🎯 Score | 💰 Salary | 📅 Posted | ✅ Skills | Apply |
- 🎯 Score MUST be a number out of 100, e.g. "87/100". Never write text like "Strong".
- 💰 Salary: use the salary value from the job listing (e.g. "USD 120k–150k/yr").
  If not available write "—".
- 📅 Posted: use the posted_at date from the job listing (e.g. "2026-06-30").
  If not available write "—".
- ✅ Skills: comma-separated matched skills, e.g. "Python, AWS, SQL". If none: "—".
- Apply MUST be an HTML link: <a href="URL" target="_blank" rel="noopener">Apply</a>
  If no URL is available write "—".
- # column: use the ABSOLUTE rank across all 50 (row 1 on page 1 = 1,
  row 1 on page 2 = 11, etc.)

PAGINATION RULES (never break):
- First response: show rows 1–10. After the table output EXACTLY:
  "📄 **Page 1 of N** · Showing **1–10** of **TOTAL** curated matches · ▶ reply **next** for more"
  (Replace N with ceil(total/10), TOTAL with actual count up to 50.)
- When user replies "next", "next page", "more", or "▶": show the next 10 rows.
  After each next-page table output EXACTLY:
  "📄 **Page P of N** · **START–END** of **TOTAL** · ◀ **prev** · ▶ **next**"
  (Omit ▶ next on the last page. Omit ◀ prev on page 1.)
- When user replies "prev", "previous", "back", or "◀": show the previous 10 rows.
- DO NOT re-score or re-rank on subsequent pages — use the same ranked list.
- DO NOT add "General Feedback", "Next Steps", "Top Recommendations", or any prose.
"""

eligibility_agent = LlmAgent(
    name="eligibility",
    model=_MODEL,
    description="Judges each opportunity against the student's profile (visa, GPA, deadline).",
    instruction=_INSTRUCTION,
    tools=[],
    before_tool_callback=guardian_before_tool,
)


def evaluate_opportunity(opp: dict) -> dict:
    """Deterministic rule-based eligibility check for a single opportunity.

    Handles both fixture field names (citizenship_required / clearance) and
    MCP seed-data field names (requires_citizenship / requires_clearance).
    """
    needs_citizenship = opp.get("citizenship_required") or opp.get("requires_citizenship")
    needs_clearance = opp.get("clearance") or opp.get("requires_clearance")

    if needs_citizenship or needs_clearance:
        return {
            "verdict": "Not eligible",
            "reason": "Requires US citizenship or security clearance; not compatible with F-1/CPT/OPT.",
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
