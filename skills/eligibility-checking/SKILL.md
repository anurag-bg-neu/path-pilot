---
name: eligibility-checking
description: |
  Decide whether a specific opportunity fits a job seeker's profile.
  Use this skill when the user asks whether they qualify for a scholarship, grant,
  internship, or job, or asks to filter a list of opportunities by eligibility.
  Do NOT use for drafting essays or for general career advice.
version: 1.1.0
license: MIT
---
# Eligibility Checking

## When to use
- The user asks "am I eligible for X?" for a scholarship, grant, or role.
- A list of opportunities must be filtered against the job seeker's profile.
- A parsed resume profile is available — rank and match jobs to the profile.

## When NOT to use
- Writing or editing emails / cover letters (use `draft-coaching`).
- Open-ended career strategy.

## Mode A — Visa / requirement check (no resume)
1. Read only the profile fields the task needs (visa status, GPA, graduation date,
   field of study) from the conversation — nothing more.
2. Read the opportunity's requirements (citizenship, clearance, GPA cutoff, deadline,
   sponsorship).
3. Compare. For each opportunity output a verdict (Eligible / Not eligible / Needs info)
   and a one-line reason citing the specific requirement.
4. Never guess a requirement that is not stated; mark it "Needs info" instead.

Output format (Mode A):
- verdict: Eligible | Not eligible | Needs info
- reason: one sentence naming the deciding requirement

## Mode B — Resume-based job matching (resume profile present)
When a RESUME PROFILE block is present in the conversation (produced by the Resume
Parser agent), switch to matching mode:

1. Identify the **target role** — the job title or role type the user explicitly asked
   for in their message (e.g. "SDE", "data engineer", "entry level software engineer").
2. Read the RESUME PROFILE: skills, experience_level, recent_titles.
3. For each job in the Discovery results compute a match score across THREE dimensions:

   **a. Role title match (0–50)**
   Does the job title match the role the user asked for?
   - Strong match (job title contains the requested role keywords): 40–50
   - Partial match (related role, e.g. "Software Developer" for "SDE"): 20–39
   - Weak / unrelated title: 0–19
   IMPORTANT: base this entirely on the job title vs the user's requested role.
   NEVER factor in the job seeker's previous employers, company names, or industry sector.

   **b. Skills match (0–35)**
   How many skills listed in the job description appear in the RESUME PROFILE skills list?
   Score proportionally to the fraction of required skills matched.
   NEVER subtract points because the job seeker's prior jobs were in a different industry.

   **c. Level match (0–15)**
   Does the job's seniority level fit the job seeker's experience_level from the profile?
   - Exact or adjacent match (entry→entry, mid→mid): full points
   - One step off (entry→mid): half points
   - Large mismatch (entry→senior): 0

4. Total score = Role + Skills + Level (max 100).
5. Rank ALL jobs by total score descending.
6. Keep the **top 50** and return them ALL in a single markdown table — no pagination.
   (Exact column layout and formatting rules are appended to this agent's instruction.)

## Anti-patterns to avoid
- Do not assume a job seeker is ineligible by default based on visa or work-authorization
  status; many roles allow CPT/OPT, sponsorship, or require no restriction at all.
- Do not expose profile fields the task did not require.
- Do not fabricate skill requirements not stated in the job listing.
- NEVER penalise or deprioritise a job because the job seeker's prior companies or industries
  differ from the hiring company's sector. Company background is irrelevant to matching.
- NEVER use field_of_study or industry to filter out roles — only use it as a tiebreaker
  if two jobs score identically on Role + Skills + Level.
- In Mode B, never show fewer than the available jobs if fewer than 20 were scraped.
- Do not require visa or work-authorization fields to be present to run Mode B — score
  citizenship/clearance restrictions only when the opportunity states them.
