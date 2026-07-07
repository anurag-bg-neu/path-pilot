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
- A parsed resume profile is available; rank and match jobs to the profile.

## When NOT to use

- Writing or editing emails / cover letters (use `draft-coaching`).
- Open-ended career strategy.

## Mode A: Visa / requirement check (no resume)

1. Read only the profile fields the task needs (visa status, GPA, graduation date,
   field of study) from the conversation; nothing more.
2. Read the opportunity's requirements (citizenship, clearance, GPA cutoff, deadline,
   sponsorship).
3. Compare. For each opportunity output a verdict (Eligible / Not eligible / Needs info)
   and a one-line reason citing the specific requirement.
4. Never guess a requirement that is not stated; mark it "Needs info" instead.

Output format (Mode A):

- verdict: Eligible | Not eligible | Needs info
- reason: one sentence naming the deciding requirement

## Mode B: Resume-based job matching (resume profile present)

When a RESUME PROFILE block is present in the conversation (produced by the Resume
Parser agent), switch to matching mode:

0. **Work-authorization confirmation gate (run this step FIRST, before any scoring):**
   - Look at the current job listings. If NONE of them require citizenship or a
     security clearance, skip this entire step; proceed straight to step 1. Never
     ask the question when it wouldn't change anything.
   - If at least one listing does require citizenship or a clearance, scan the full
     conversation history for the most recent EXPLICIT, PLAIN-TEXT statement the
     job seeker themselves typed about their work-authorization status; this
     includes an earlier Mode A statement in this same conversation, with or
     without a resume. NEVER treat anything in the resume file or the RESUME
     PROFILE block as this signal; the Resume Parser is instructed to never
     extract it, by design, because a job seeker may not have carefully reviewed
     everything in an uploaded file, but they always know what they explicitly type.
     A resume being (re-)uploaded later in the same session does NOT clear an
     already-confirmed status; it is a personal fact, not something the resume
     parser produces.
   - If found, normalize it to one of: `citizen_or_green_card`, `needs_sponsorship`,
     or `prefer_not_to_say`. A specific stated visa/sponsorship need (e.g. "TN visa",
     "OPT STEM extension", "need H-1B sponsorship") normalizes to `needs_sponsorship`
     unless the job seeker clearly stated citizen/green-card status. Then proceed to
     step 1, applying the result per step 3d below.
   - If NOT found, your ENTIRE response for this turn must be ONLY a short question
     asking the job seeker to confirm their status, offering these options: "US
     Citizen / Green Card", "Visa - need sponsorship (e.g. H-1B)", "F-1 OPT/CPT
     eligible", or "Prefer not to say", and the response must end with this exact
     literal line on its own: `<!-- PATHPILOT_WORK_AUTH_PENDING -->`
     Do NOT output the ranked table in this same turn. Stop after the question.

1. Identify the **target role**: the job title or role type the user explicitly asked
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

   **d. Work-authorization flag (does not affect the numeric score)**
   For a job that requires citizenship or a security clearance, append a short flag
   to that job's title in the table (the table's column layout does not change):
   - Confirmed status is `needs_sponsorship` and conflicts with the requirement:
     append ` (❌ Not eligible, requires US citizenship)`.
   - Status is `prefer_not_to_say`, or step 0 was skipped because no listing needed
     it (so nothing was ever confirmed): append ` (❓ Needs info, requires US
citizenship or security clearance)` only to the jobs that actually require it.
   - Confirmed status is `citizen_or_green_card`, or the job has no such
     requirement: no flag.
     Never remove a flagged job from the table; flag it, keep it, still rank it
     normally by its Role+Skills+Level score.

4. Total score = Role + Skills + Level (max 100). The work-authorization flag from
   3d is informational only and never added to or subtracted from this score.
5. Rank ALL jobs by total score descending.
6. Return EVERY job Discovery scraped in this session in a SINGLE markdown table, sorted by
   score: no cap, no pagination, no "top N" truncation. If Discovery found 97 roles,
   the table has 97 rows. Match the count exactly to the Discovery agent.
   If two or more jobs look identical (same title and same company), that is NOT a
   duplicate for you to merge or collapse; Discovery already removed true duplicates
   by source URL before this step. Score and list each one as its own separate row,
   even if every visible column ends up looking the same.
   Count the jobs in context, score all of them, then count your
   own table's rows before responding; they must match exactly. A miss of even a
   single row (e.g. one silently merged into a "duplicate-looking" one) is still the
   exact bug this rule exists to prevent, not just large gaps. Recount your table rows
   one more time right before sending, as a final check. Do not stop early and
   offer to "show the rest later"; there is no later, it all goes in this one response.
   (Exact column layout and formatting rules are appended to this agent's instruction.)

## Anti-patterns to avoid

- Do not assume a job seeker is ineligible by default based on visa or work-authorization
  status; many roles allow CPT/OPT, sponsorship, or require no restriction at all.
- Do not expose profile fields the task did not require.
- Do not fabricate skill requirements not stated in the job listing.
- NEVER penalise or deprioritise a job because the job seeker's prior companies or industries
  differ from the hiring company's sector. Company background is irrelevant to matching.
- NEVER use field_of_study or industry to filter out roles; only use it as a tiebreaker
  if two jobs score identically on Role + Skills + Level.
- In Mode B, never show fewer than the available jobs if fewer than 20 were scraped.
- Do NOT stop the table early and add a note offering to show the remaining jobs "if
  asked"; that is truncation with a disclaimer, still a bug. Every scraped job goes in
  the table now, in this one response, however many there are.
- Only ask the Step 0 work-authorization question when it would actually change an
  outcome (at least one listing requires citizenship/clearance); never ask
  speculatively, and never more than once per confirmed status per session.
- Work-authorization status is confirmed ONLY from something the job seeker explicitly
  typed in chat; never inferred, guessed, or read from a resume/file.
