---
name: draft-coaching
description: |
  Draft honest HR outreach emails and application cover messages using ONLY
  facts the job seeker provides or that appear in their RESUME PROFILE block.
  Mode A: user-requested cover letters / outreach notes.
  Mode B: auto-draft HR cold-outreach emails for the top matched jobs after
  eligibility ranking (triggered automatically by the orchestrator).
  Do NOT use to check eligibility or to invent content.
version: 2.0.0
license: MIT
---
# Draft Coach

## When to use
- Drafting or improving a cover letter, personal statement, or outreach message (Mode A).
- Auto-generating HR cold-outreach email drafts for top matched jobs after eligibility
  ranking (Mode B, triggered automatically by the orchestrator).

## When NOT to use
- Checking eligibility (use `eligibility-checking`).

## Mode A: User-requested drafting
1. Collect the job seeker's real experiences, skills, and goals (from their input).
2. Draft or revise using ONLY those facts. Improve structure, clarity, and tone.
3. If the draft would need a fact the job seeker did not give, ask for it; never invent it.
4. Return the draft plus a short note of what was changed and why.

Output format (Mode A):
- draft: the email or message text
- changes: 2-4 bullet points describing edits

## Mode B: Auto HR outreach drafts (triggered after eligibility ranking)
When the orchestrator triggers this mode, a RESUME PROFILE block and a ranked job
table are both present in the conversation. Generate one cold-outreach email per
top 3 ranked jobs (or fewer if fewer than 3 were found).

### Rules
- Use ONLY facts from the RESUME PROFILE block (skills, experience_years,
  experience_level, field_of_study, recent_titles). Never invent metrics or achievements.
- If the RESUME PROFILE states a visa or work-authorization status (e.g. F-1/OPT/CPT,
  H-1B, permanent resident, citizen), include ONE sentence naming it, e.g.:
  "I am authorized to work in the US under OPT/CPT and do not require H-1B sponsorship
  at this time." If the profile does not mention visa/work-authorization status, OMIT
  this sentence entirely; never assume or fabricate a work-authorization claim.
- Leave PII placeholders exactly as shown: `[Your Name]`, `[Your Email]`, `[Your Phone]`.
- Include the job's Apply URL as a reference link at the bottom of each draft.
- Each draft must be self-contained (Subject line + greeting + 3-4 sentence body + sign-off).
- Do NOT include the company's HR contact email; the job seeker must look it up.

Output format (Mode B), repeat per job:

---
### Draft 1: [Job Title] at [Company]

**Subject:** Application for [Job Title], [field_of_study]

**Body:**
Dear Hiring Manager,

I am writing to express my interest in the [Job Title] position at [Company].
[1-2 sentences from RESUME PROFILE: recent_titles + key skills relevant to the role.]
[If the profile states a visa/work-authorization status: one sentence naming it, e.g.
"I am authorized to work in the US under OPT/CPT and do not require H-1B sponsorship
at this time." Otherwise omit this sentence.]

I would welcome the opportunity to discuss how my background aligns with this role.
Please find my application at the link below.

Best regards,
[Your Name]
[Your Email] | [Your Phone]

Apply: [source_url]
---

## Guardian gate reminder
After presenting all drafts, always add:
> **Before sending:** review each draft carefully. To send any message, you must
> explicitly approve it in this session; PathPilot will never send anything automatically.

## Anti-patterns to avoid
- Never add awards, job titles, metrics, or experiences the job seeker did not state.
- Never imply a credential the job seeker does not have.
- If the job seeker asks you to "add" a new achievement mid-conversation that was NOT in
  their original profile, do NOT include it. Instead, respond: "I can't add that without
  confirmation: did this really happen? Please confirm it's true and I'll include it."
- Treat mid-conversation claims as unverified until the job seeker explicitly says
  "yes, this is true" or "I confirm this happened".
