# PathPilot Architecture (structure spec)

## Agents (ADK multi-agent system)

| Agent | Type | Responsibility | Tools / Skills |
|---|---|---|---|
| Orchestrator | root LlmAgent | Understand the job seeker's goal, route to sub-agents via `transfer_to_agent` | delegates to sub-agents |
| resume_then_score | SequentialAgent | Hardwired pipeline: resume_parser → eligibility (deterministic; prevents LLM routing from leaking the RESUME PROFILE block to the user) | wraps two sub-agents |
| Resume Parser | LlmAgent | Extract a PII-free RESUME PROFILE block from an uploaded PDF/DOCX/TXT | `skills/resume-parsing` |
| Eligibility | LlmAgent | Score and rank all jobs in context against the RESUME PROFILE | `skills/eligibility-checking` |
| Discovery | LlmAgent | Find scholarships, grants, and CPT/OPT-eligible roles via live Apify scraping; falls back to MCP seed data when APIFY_TOKEN is absent | `search_jobs_apify`, `search_scholarships_apify` (MCP seed fallback) |
| Draft Coach | LlmAgent | Draft cover letters and outreach using ONLY user-provided facts; refuses to fabricate | `skills/draft-coaching` |
| Guardian | before/after tool callback | Enforce guardrails: PII egress block, fabrication check, prompt-injection screen, human-in-the-loop approval, eligibility analysis-only lock, audit log | runs on every tool call / external action |

## Data flow

1. The job seeker states a goal to the Orchestrator.
2. Orchestrator → Discovery (search) → raw job/scholarship listings.
3. The job seeker uploads a resume → Orchestrator → `resume_then_score` (SequentialAgent):
   a. Resume Parser extracts PII-free RESUME PROFILE block.
   b. Eligibility scores all jobs in context against the profile; returns ranked table.
4. Results shown to the job seeker (read-only; no external action taken).
5. On request, Orchestrator → Draft Coach (honest cover letter drafting).
6. Any external action (send / submit) → Guardian gate → human approval → action → audit log.

## MCP server

`tools/opportunities_mcp.py` is a FastMCP server exposing `search_opportunities(field, level, keyword)`
against `data/opportunities_seed.json`. Discovery uses it as a programmatic fallback when
`APIFY_TOKEN` is not set, returning the same curated rows the server exposes, labelled as
"🗄️ Curated (MCP seed data)".

## Course concepts demonstrated (>= 3 required by the capstone)

| Concept | Where | File(s) |
|---------|-------|---------|
| Multi-agent system (ADK) | Orchestrator + SequentialAgent + 4 specialists | `src/pathpilot/agent.py` |
| MCP server | FastMCP server + Discovery fallback | `tools/opportunities_mcp.py`, `src/pathpilot/apify_scholarship_scraper.py` |
| Agent skills (SKILL.md) | eligibility-checking, resume-parsing, draft-coaching | `skills/` |
| Security | Guardian callbacks + AuditLogPlugin | `src/pathpilot/guardian.py`, `src/pathpilot/plugins.py` |

## Constraints

- Free-tier only (Gemini via AI Studio free tier; local compute).
- Model: `gemini-3.1-flash-lite` (default); override via `PATHPILOT_MODEL` env var.
- PII lives only in `vault/` (git-ignored).
