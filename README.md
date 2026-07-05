# PathPilot

**Privacy-first, multi-agent scholarship and career assistant for all job seekers.**

- Built for the [Kaggle Vibe Coding Capstone](https://www.kaggle.com/competitions/vibecoding-agents-capstone-project) — *Agents for Good* track. 
- [5-Day AI Agents: Intensive Vibe Coding Course With Google](https://www.kaggle.com/learn-guide/5-day-agents-vibecoding) — *Agentic AI Course*
- Powered by [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and Gemini.

---

## What it does

Job seekers — students, career changers, and international professionals alike — face a common challenge: most job search tools ignore individual eligibility factors (work authorization, field, experience level) and carry the risk of AI-fabricated applications. PathPilot solves this with a multi-agent pipeline that is honest, private, and safe by design for every job seeker.

| Step | Agent | What happens |
|------|-------|-------------|
| 1 | **Discovery** | Finds scholarships, grants, and CPT/OPT-eligible roles via live Apify scraping (Indeed, LinkedIn, Glassdoor, ZipRecruiter, Jobright) |
| 2 | **Resume Parser** | Extracts a PII-free skills profile from an uploaded resume (PDF/DOCX/TXT) |
| 3 | **Eligibility** | Scores and ranks job listings against the job seeker's profile; ranked results in a single response |
| 4 | **Draft Coach** | Drafts cover letters and outreach using *only* facts the job seeker provides |
| 5 | **Guardian** | Enforces all safety guardrails; pauses for human approval before any external action |

---

## Security guardrails (Day 4 — Agents for Good)

| Guardrail | Implementation |
|-----------|---------------|
| Human-in-the-loop | Guardian gate pauses the runner; nothing is sent without explicit approval |
| No fabrication | Draft Coach refuses to invent awards, titles, or metrics; output is audited |
| PII stays local | Resume content parsed locally into a PII-free profile; raw text never forwarded |
| Prompt-injection defense | Fetched web content is screened and redacted before the LLM sees it |
| Audit log | `AuditLogPlugin` emits structured JSON for every agent turn and tool call |
| Free-tier only | Gemini Flash via AI Studio free tier — no billing required |

---

## Architecture

```
pathpilot_orchestrator  (root LlmAgent)
├── resume_then_score   (SequentialAgent — hardwired pipeline)
│   ├── resume_parser   (LlmAgent — extracts PII-free profile)
│   └── eligibility     (LlmAgent — scores & ranks jobs vs profile)
├── discovery           (LlmAgent + Apify tools — job/scholarship search)
└── draft_coach         (LlmAgent + SKILL.md + approval gate)

guardian.py             (before_tool_callback on all agents)
plugins.py              (AuditLogPlugin — structured PII-free logging)
apify_jobs_scraper.py   (parallel LinkedIn + Indeed + agentx scraping)
apify_scholarship_scraper.py  (scholarship search via web)
```

---

## Quick start

```bash
# 1. Clone and create environment
git clone https://github.com/anurag-bg-neu/path-pilot.git
cd path-pilot
python -m venv .venv && .venv\Scripts\activate   # Windows
# python -m venv .venv && source .venv/bin/activate  # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API keys (free tier)
cp .env.example .env
# Edit .env — add GOOGLE_API_KEY and optionally APIFY_TOKEN

# 4. Run the agent backend
adk web src/pathpilot --no-reload   # --no-reload required on Windows

# 5. Run the React frontend (separate terminal)
cd ui && npm install && npm run dev

# 6. Run the test suite
pytest
```

---

## Project layout

```
path-pilot/
├── specs/                  # Gherkin feature spec (source of truth)
├── skills/                 # SKILL.md capability cards
│   ├── eligibility-checking/
│   ├── resume-parsing/
│   └── draft-coaching/
├── src/pathpilot/          # ADK agents
│   ├── agent.py            # Orchestrator + SequentialAgent pipeline + App
│   ├── guardian.py         # Safety guardrails (before_tool_callback)
│   ├── plugins.py          # Structured audit logger (AuditLogPlugin)
│   ├── apify_jobs_scraper.py        # Parallel LinkedIn / Indeed / agentx scraper
│   ├── apify_scholarship_scraper.py # Scholarship web scraper
│   └── agents/
│       ├── discovery.py
│       ├── eligibility.py
│       ├── resume_parser.py
│       └── draft_coach.py
├── ui/                     # React + Vite + TypeScript frontend
│   └── src/
│       ├── App.tsx         # Chat UI with history, pagination, animations
│       ├── api.ts          # ADK SSE streaming client
│       └── types.ts
├── tests/
│   └── test_pathpilot.py   # pytest-bdd scenarios (all 6 green)
└── vault/                  # Local PII only — git-ignored
```

---

## Test results

```
tests/test_pathpilot.py::test_find_scholarships_that_match_the_job_seekers_field_and_level PASSED
tests/test_pathpilot.py::test_filter_opportunities_by_workauthorization_eligibility      PASSED
tests/test_pathpilot.py::test_require_human_approval_before_any_external_action          PASSED
tests/test_pathpilot.py::test_refuse_to_fabricate_achievements_in_an_essay               PASSED
tests/test_pathpilot.py::test_treat_fetched_web_content_as_untrusted_data                PASSED
tests/test_pathpilot.py::test_keep_personal_data_local                                   PASSED

6 passed in 6s
```

---

## Concept → file map (for judges)

| Course concept | Implementation | Key file(s) |
|----------------|---------------|-------------|
| Multi-agent system (ADK) | Orchestrator + `resume_then_score` SequentialAgent + 4 sub-agents | `src/pathpilot/agent.py` |
| MCP server | FastMCP server + Discovery seed fallback when `APIFY_TOKEN` absent | `tools/opportunities_mcp.py`, `src/pathpilot/apify_scholarship_scraper.py` |
| Agent skills | `eligibility-checking`, `resume-parsing`, `draft-coaching` SKILL.md cards | `skills/` |
| Security | Guardian callbacks (HITL, PII, injection, eligibility lock) + AuditLogPlugin | `src/pathpilot/guardian.py`, `src/pathpilot/plugins.py` |

---

## Demo video

▶ [YouTube demo](https://youtu.be/TODO) — 5-minute walkthrough: job search → FAANG filter → resume upload → ranked eligibility table → cover letter draft → human-in-the-loop approval gate

---

## Course concepts demonstrated

- **Multi-agent system** — Orchestrator delegates to specialist agents; SequentialAgent for deterministic resume→eligibility pipeline (Day 1, Day 3)
- **Live data tools** — Discovery queries Apify actors (LinkedIn, Indeed, Glassdoor, ZipRecruiter, Jobright) in parallel (Day 2)
- **Agent skills** — `eligibility-checking`, `resume-parsing`, `draft-coaching` as SKILL.md capability cards (Day 3)
- **Security** — Human-in-the-loop, PII protection, prompt-injection defense, anti-fabrication, audit trail (Day 4)

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes | Gemini API key from [AI Studio](https://aistudio.google.com) (free tier) |
| `PATHPILOT_MODEL` | No | Override the Gemini model (default: `gemini-3.1-flash-lite`) |
| `APIFY_TOKEN` | No | Apify API token for live job scraping — [get one free at apify.com](https://apify.com) |

---

## License

MIT
