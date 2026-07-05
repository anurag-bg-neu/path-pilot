"""Shared pytest-bdd fixtures for PathPilot BDD tests."""
import pytest


@pytest.fixture
def ctx() -> dict:
    """Mutable context dict shared across Given/When/Then steps in one scenario."""
    return {}


@pytest.fixture
def job_seeker_profile() -> dict:
    """Minimal job seeker profile stored in the vault — no real PII here."""
    return {
        "visa": "F-1",
        "gpa": 3.5,
        "graduation": "2025-05",
        "field": "Computer Science",
        "level": "masters",
    }


@pytest.fixture
def roles_list() -> list[dict]:
    # Covers the seed-data cases the verify step checks:
    # role-01 / sch-02 -> Not eligible; int-01 / int-02 -> Eligible
    return [
        # int-01 equivalent
        {
            "title": "Backend SWE Intern - Cloud Platform",
            "citizenship_required": False,
            "clearance": False,
            "cpt_opt_compatible": True,
        },
        # role-01 equivalent
        {
            "title": "Defense Systems Software Engineer",
            "citizenship_required": True,
            "clearance": True,
        },
        # int-02 equivalent
        {
            "title": "ML Research Internship - AI Lab",
            "citizenship_required": False,
            "clearance": False,
            "cpt_opt_compatible": True,
        },
        # sch-02 equivalent
        {
            "title": "Federal STEM Fellowship (US Citizens only)",
            "citizenship_required": True,
            "clearance": False,
        },
    ]
