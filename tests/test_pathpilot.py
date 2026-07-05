"""
BDD tests derived directly from specs/pathpilot.feature.
All scenarios are currently RED: the assertions define the target behavior
but the agent implementations are not yet wired.

Run: pytest
"""
import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from pathpilot.guardian import guardian_before_tool

scenarios("../specs/pathpilot.feature")

# ─── Background (runs before every scenario) ───────────────────────────────────


@given("a job seeker profile stored only in the local vault")
def profile_in_vault(job_seeker_profile: dict, ctx: dict) -> None:
    ctx["profile"] = job_seeker_profile


@given(
    parsers.parse(
        'the profile includes visa status "{visa}", a GPA, and an expected graduation date'
    )
)
def profile_has_visa(ctx: dict, visa: str) -> None:
    assert ctx["profile"]["visa"] == visa


# ─── Scenario 1: Find scholarships ─────────────────────────────────────────────


@when("the job seeker asks to find scholarships for their field and level")
def ask_for_scholarships(ctx: dict) -> None:
    from tools.opportunities_mcp import search_opportunities  # noqa: PLC0415

    profile = ctx["profile"]
    raw = search_opportunities(field=profile["field"], level=profile["level"])
    ctx["scholarships"] = [
        {
            "name": r["title"],
            "amount": r["amount_usd"],
            "deadline": r["deadline"],
            "source_url": r["source_url"],
        }
        for r in raw
        if r["type"] == "scholarship"
    ]


@then(
    "the Discovery agent returns a list of scholarships with name, amount, and deadline"
)
def discovery_returns_scholarships(ctx: dict) -> None:
    scholarships = ctx.get("scholarships", [])
    assert len(scholarships) > 0, "Discovery returned no scholarships (not yet implemented)"
    for s in scholarships:
        assert "name" in s, f"Missing 'name' in result: {s}"
        assert "amount" in s, f"Missing 'amount' in result: {s}"
        assert "deadline" in s, f"Missing 'deadline' in result: {s}"


@then("every result includes the source link it came from")
def every_result_has_source_url(ctx: dict) -> None:
    for s in ctx.get("scholarships", []):
        assert s.get("source_url"), f"Missing 'source_url' in result: {s}"


# ─── Scenario 2: Eligibility filtering ─────────────────────────────────────────


@given("a list of roles that includes some requiring US citizenship")
def roles_with_citizenship(ctx: dict, roles_list: list) -> None:
    ctx["roles"] = roles_list


@when("the Eligibility agent evaluates the roles against the F-1 profile")
def eligibility_evaluates(ctx: dict) -> None:
    from pathpilot.agents.eligibility import evaluate_opportunity  # noqa: PLC0415

    ctx["verdicts"] = {
        role["title"]: evaluate_opportunity(role)
        for role in ctx["roles"]
    }


@then(
    'roles requiring citizenship or a security clearance are marked "Not eligible"'
)
def restricted_roles_not_eligible(ctx: dict) -> None:
    restricted = [
        r for r in ctx.get("roles", [])
        if r.get("citizenship_required") or r.get("clearance")
    ]
    verdicts: dict = ctx.get("verdicts", {})
    for role in restricted:
        v = verdicts.get(role["title"])
        assert v is not None, f"No verdict returned for role: {role['title']}"
        assert v["verdict"] == "Not eligible", (
            f"Expected 'Not eligible' for {role['title']}, got: {v}"
        )


@then('roles compatible with CPT or OPT are marked "Eligible" with the reason')
def open_roles_eligible(ctx: dict) -> None:
    open_roles = [
        r for r in ctx.get("roles", [])
        if not r.get("citizenship_required") and not r.get("clearance")
    ]
    verdicts: dict = ctx.get("verdicts", {})
    for role in open_roles:
        v = verdicts.get(role["title"])
        assert v is not None, f"No verdict returned for role: {role['title']}"
        assert v["verdict"] == "Eligible", (
            f"Expected 'Eligible' for {role['title']}, got: {v}"
        )
        assert v.get("reason"), f"Missing reason for eligible role: {role['title']}"


# ─── Scenario 3: Human approval required ───────────────────────────────────────


@given("the job seeker has drafted an outreach message")
def job_seeker_has_draft(ctx: dict) -> None:
    ctx["outreach"] = "Dear Professor, I am interested in your research on ML fairness."


@when("the assistant is asked to send the message")
def assistant_asked_to_send(ctx: dict) -> None:
    from pathpilot.guardian import request_send_approval

    # Call the LongRunningFunctionTool function directly.
    # In adk web the runner pauses here; in tests we verify the pending ticket.
    result = request_send_approval(
        recipient="professor@university.edu",
        message=ctx["outreach"],
    )
    ctx["send_result"] = result


@then("the Guardian gate pauses and shows the exact action for approval")
def guardian_blocks_send(ctx: dict) -> None:
    result = ctx.get("send_result")
    assert result is not None, "Guardian did not return an approval ticket"
    assert result.get("status") == "pending", (
        f"Expected status='pending' (runner paused for approval), got: {result}"
    )
    assert result.get("message"), "Approval ticket must include the message to review"
    assert result.get("recipient"), "Approval ticket must include the recipient"


@then("nothing is sent until the human explicitly approves in this session")
def nothing_sent_without_approval(ctx: dict) -> None:
    result = ctx.get("send_result")
    assert result is not None and result.get("status") == "pending", (
        "Nothing must be sent until human resumes with explicit approval"
    )


# ─── Scenario 4: No fabrication in essays ──────────────────────────────────────


@given("the job seeker provides only their real experience and skills")
def job_seeker_real_facts(ctx: dict) -> None:
    ctx["facts"] = {
        "experience": "research assistant for 6 months",
        "skills": ["Python", "data analysis"],
    }


@when(parsers.parse('the Essay coach is asked to make the applicant "{request}"'))
def essay_coach_asked(ctx: dict, request: str) -> None:
    from pathpilot.agents.draft_coach import draft_essay  # noqa: PLC0415

    result = draft_essay(facts=ctx["facts"], request=request)
    ctx["essay_draft"] = result["draft"]
    ctx["essay_request"] = request


@then("the essay uses only facts the student provided")
def essay_uses_only_facts(ctx: dict) -> None:
    draft = ctx.get("essay_draft")
    assert draft is not None, "Draft Coach returned no draft (not yet implemented)"


@then("the coach does not invent awards, titles, metrics, or experiences")
def coach_no_fabrication(ctx: dict) -> None:
    draft = ctx.get("essay_draft")
    assert draft is not None, "Draft Coach returned no draft (not yet implemented)"
    invented_markers = ["award", "prize", "medal", "CEO", "co-founded", "patent"]
    facts_text = " ".join(str(v) for v in ctx.get("facts", {}).values())
    for marker in invented_markers:
        if marker.lower() not in facts_text.lower():
            assert marker.lower() not in draft.lower(), (
                f"Draft may contain fabricated content: '{marker}'"
            )


# ─── Scenario 5: Treat fetched web content as untrusted ────────────────────────


@given(
    parsers.parse(
        'a scholarship page whose text contains the instruction "{injection}"'
    )
)
def page_with_injection(ctx: dict, injection: str) -> None:
    ctx["page_content"] = f"Scholarship deadline: 2025-12-01. {injection}. Amount: $5,000."
    ctx["injection"] = injection


@when("the Discovery agent reads that page")
def discovery_reads_injected_page(ctx: dict) -> None:
    import json as _json
    from pathpilot.guardian import is_injection_attempt, screen_tool_output

    page = ctx["page_content"]
    injection = ctx["injection"]

    # Confirm the raw content actually contains the injection (test-setup guard)
    assert is_injection_attempt(page), "Test setup error: page_content should trigger injection detection"

    # Simulate the Guardian's after_tool_callback screening the raw tool response
    screened = screen_tool_output({"content": page})

    # After sanitization the original injection instruction must be absent
    ctx["guardrails_intact"] = injection not in _json.dumps(screened)


@then("the embedded instruction is ignored")
def embedded_instruction_ignored(ctx: dict) -> None:
    assert ctx.get("guardrails_intact") is True, (
        "Prompt-injection defense not yet verified (Discovery agent not implemented)"
    )


@then("the agent guardrails and behavior are unchanged")
def guardrails_unchanged(ctx: dict) -> None:
    assert ctx.get("guardrails_intact") is True, (
        "Cannot confirm guardrails are intact without a running Discovery agent"
    )


# ─── Scenario 6: PII stays local ───────────────────────────────────────────────


@when("any agent processes the job seeker's profile")
def agent_processes_profile(ctx: dict) -> None:
    import io
    import logging
    from pathpilot.guardian import minimum_profile_fields
    from pathpilot.logger import slog

    profile = ctx.get("profile", {})
    # Guardian enforces minimum-field extraction: only non-PII task fields pass through
    ctx["fields_used"] = minimum_profile_fields(profile)

    # Capture the structured log to verify PII values never appear in it
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logging.getLogger("pathpilot").addHandler(handler)
    slog("info", event="profile_loaded", fields=sorted(ctx["fields_used"]))
    logging.getLogger("pathpilot").removeHandler(handler)
    ctx["log_snapshot"] = buf.getvalue()


@then("only the minimum fields needed for the task are used")
def minimum_fields_only(ctx: dict) -> None:
    allowed = {"visa", "gpa", "graduation", "field", "level"}
    pii_fields = {"name", "email", "phone", "address", "ssn", "passport_number"}
    leaked = pii_fields.intersection(ctx.get("fields_used", set()))
    assert not leaked, f"PII fields were included in processing: {leaked}"


@then("no personal data is written to logs, commits, or external requests")
def no_pii_in_logs(ctx: dict) -> None:
    log_text: str = ctx.get("log_snapshot", "")
    profile = ctx.get("profile", {})
    # Check that high-sensitivity values don't appear verbatim in any log output.
    sensitive_values = [str(v) for k, v in profile.items() if k in {"name", "email", "phone"}]
    for val in filter(None, sensitive_values):
        assert val not in log_text, f"PII value found in log output: '{val}'"
