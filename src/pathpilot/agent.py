"""Root Orchestrator agent — ADK entry point.

`adk web src/pathpilot` discovers `app` (checked first) or `root_agent` from
this module via __init__.py.  The App bundles the orchestrator with the
AuditLogPlugin so every invocation is structured-logged automatically.
"""
import os

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.apps.app import App

from .agents.discovery import discovery_agent
from .agents.eligibility import eligibility_agent
from .agents.draft_coach import draft_coach_agent
from .agents.resume_parser import resume_parser_agent
from .guardian import guardian_before_tool, route_work_auth_confirmation_reply
from .plugins import AuditLogPlugin

_MODEL = os.getenv("PATHPILOT_MODEL", "gemini-3.1-flash-lite")

# Hardwired pipeline: resume_parser → eligibility (no LLM routing needed between them).
# This replaces the fragile "Rule 1" instruction that gemini-flash-lite kept ignoring.
resume_then_score = SequentialAgent(
    name="resume_then_score",
    description=(
        "Parse the uploaded resume into a PII-free profile, then immediately score "
        "all job listings already in context for eligibility. "
        "Call this whenever the user attaches a resume file."
    ),
    sub_agents=[resume_parser_agent, eligibility_agent],
)

_INSTRUCTION = """\
You are PathPilot, a privacy-first multi-agent assistant for job seekers —
including students, career changers, and international professionals.

You route requests to sub-agents using transfer_to_agent. Never answer directly
unless no sub-agent applies.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROUTING TABLE — first matching row wins
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. User attached a file (PDF / DOCX / TXT) AND job listings exist in context:
   → transfer_to_agent(agent_name="resume_then_score")

2. User attached a file (PDF / DOCX / TXT) AND no job listings in context yet:
   → transfer_to_agent(agent_name="discovery") first to fetch jobs,
     then transfer_to_agent(agent_name="resume_then_score")

3. User asks for jobs / roles / internships / positions (no file):
   → transfer_to_agent(agent_name="discovery")
   → After discovery returns, say ONCE:
     "Upload your resume (📎) to get a personalised eligibility score."

4. User asks for scholarships / grants / funding / financial aid:
   → transfer_to_agent(agent_name="discovery")

5. User asks for cover letter / outreach drafting:
   → transfer_to_agent(agent_name="draft_coach")

6. Your immediately preceding message asked the job seeker to confirm their
   work-authorization status (a Step 0 eligibility question), and this new user
   message answers it (states citizenship, green card, a visa type, a
   sponsorship need, or explicitly declines to say):
   → transfer_to_agent(agent_name="eligibility") — SILENTLY. Output NOTHING of
     your own before this call: no "thank you", no summary of what you're
     about to do, no restating their answer. The very first thing the user
     sees in this turn must be eligibility's own response.

7. User requests a real-world action (send email, submit form, post):
   → route through guardian, require explicit approval, log.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ABSOLUTE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- NEVER display any RESUME PROFILE block to the user.
- NEVER call eligibility without a RESUME PROFILE already in context.
- NEVER call discovery more than once per user turn.
- NEVER fabricate listings, skills, scores, or credentials.
- NEVER expose PII (name, email, phone, address).
- Every transfer_to_agent call is SILENT — never narrate the handoff itself
  ("I am now transferring you to...", "Thank you for providing...", "Note:
  since you have already..."). The sub-agent's own response IS the reply.
"""

root_agent = LlmAgent(
    name="pathpilot_orchestrator",
    model=_MODEL,
    description=(
        "PathPilot — multi-agent job seeker assistant. "
        "Upload resume + describe jobs for a ranked eligibility match. "
        "Say 'scholarship' to search for funding."
    ),
    instruction=_INSTRUCTION,
    sub_agents=[resume_then_score, discovery_agent, draft_coach_agent],
    before_tool_callback=guardian_before_tool,
    # Deterministically routes a reply to eligibility's work-auth confirmation
    # question (see guardian.py) — bypasses this LLM call for that one turn so
    # the handoff can't be mis-routed the way pure instruction-based routing
    # once was for resume_then_score (see comment above).
    before_model_callback=route_work_auth_confirmation_reply,
)

# App bundles root_agent + AuditLogPlugin.
# AgentLoader checks for `app` before `root_agent`, so adk web picks this up
# and every invocation is structured-logged via the plugin.
app = App(
    name="pathpilot",
    root_agent=root_agent,
    plugins=[AuditLogPlugin()],
)
