# PathPilot Architecture (structure spec)

## Agents (ADK multi-agent system)

| Agent | Type | Responsibility | Tools / Skills |
|---|---|---|---|
| Orchestrator | root LlmAgent | Understand the student's goal, route to sub-agents, assemble the final answer | delegates to sub-agents |
| Discovery | LlmAgent | Find scholarships, grants, and roles | web/search tool via MCP or ADK tool |
| Eligibility | LlmAgent | Judge each opportunity against the student profile (visa, GPA, deadline) | `skills/eligibility-checking` |
| Essay Coach | LlmAgent | Draft and critique essays / outreach using ONLY user-provided facts | `skills/essay-coaching` |
| Guardian | pre/post hook + gate | Enforce guardrails: PII egress block, fabrication check, prompt-injection screen, human-in-the-loop approval, audit log | runs on every tool call / external action |

## Data flow
1. Student states a goal to the Orchestrator.
2. Orchestrator -> Discovery (search) -> raw opportunities.
3. Discovery -> Eligibility -> opportunities labelled Eligible / Not eligible (+ reason).
4. Results shown to the student (read-only; no external action taken).
5. On request, Orchestrator -> Essay Coach (honest drafting).
6. Any external action (send / submit) -> Guardian gate -> human approval -> action -> audit log.

## Course concepts demonstrated (>= 3 required by the capstone)
- Multi-agent system (ADK): Orchestrator + 4 specialists.        [Day 1, Day 3]
- MCP / tools: Discovery reaches external data through a tool or MCP server.  [Day 2]
- Agent skills: `eligibility-checking`, `essay-coaching` as SKILL.md folders. [Day 3]
- Security: the Guardian implements human-in-the-loop, PII protection,
  prompt-injection defense, anti-fabrication, and an audit trail.            [Day 4]

## Constraints
- Free-tier only (Gemini via AI Studio free tier; local compute).
- Model: `gemini-flash-latest`.
- PII lives only in `vault/` (git-ignored).
