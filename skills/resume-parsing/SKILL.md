---
name: resume-parsing
description: |
  Extract a structured, PII-free skills profile from a user's resume.
  Use when the user provides resume text or a resume file and wants job matching.
version: 1.0.0
license: MIT
---
# Resume Parsing

## When to use
- The user pastes resume text or uploads a resume file.
- A PII-free profile is needed to match and rank job or scholarship results.

## When NOT to use
- The user has not provided a resume — ask them to paste it first.
- Writing or editing emails / cover letters (use `draft-coaching`).

## Workflow
1. Read the resume content from the conversation.
2. Extract ONLY these fields — nothing else:
   - `skills`: list of technical skills, languages, frameworks, tools
   - `experience_years`: approximate total years of work/internship experience (integer)
   - `experience_level`: one of "student", "entry", "mid", "senior"
   - `education_level`: one of "Undergraduate", "Graduate", "PhD"
   - `field_of_study`: e.g. "Computer Science", "Data Science", "Electrical Engineering"
   - `recent_titles`: up to 3 most recent job/internship titles held
3. STRIP all PII — never include: name, email, phone, address, LinkedIn URL, GitHub URL,
   university name, graduation year, GPA, nationality, visa status.
4. Output the profile as a clearly labelled block so Eligibility can use it.

## Output format
```
RESUME PROFILE (PII-free):
- Skills: Python, SQL, React, AWS, TensorFlow
- Experience: 1 year (entry level)
- Education: Graduate (Computer Science)
- Recent titles: Software Engineer Intern, Research Assistant
```

## Anti-patterns to avoid
- Do not echo the user's name, contact details, or any identifying information.
- Do not infer visa status or nationality from the resume.
- Do not fabricate skills not present in the resume.
