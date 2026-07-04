"""Apify scholarship scraper tool — live scholarships via majestic_fund/the-scholarship-scraper-actor."""
import logging
import os
from typing import Any

_ACTOR_ID = "majestic_fund/the-scholarship-scraper-actor"

# Hard guardrail: sent to the actor AND used as a post-cap.
# Never increase this without explicit human approval — each result consumes Apify credits.
_MAX_SCHOLARSHIPS = 5

log = logging.getLogger(__name__)


def _extract(item: dict[str, Any], *keys: str, fallback: str = "") -> str:
    """Return the first non-empty value found among the given keys."""
    for key in keys:
        val = item.get(key)
        if val and str(val).strip() not in ("", "None", "null", "N/A", "n/a"):
            return str(val).strip()
    return fallback


def search_scholarships_apify(
    keyword: str,
    education_level: str = "",
    field_of_study: str = "",
    country: str = "USA",
) -> list[dict[str, Any]]:
    """Search live scholarships from Scholarships.com, Fastweb, and College Board via Apify.

    IMPORTANT — only call this tool when the user explicitly asks for scholarships,
    grants, or financial aid. Do NOT call it for job searches.
    Call this AT MOST ONCE per user message. Returns at most 5 scholarships.

    Args:
        keyword: Search terms, e.g. "STEM international student F-1" or "computer science graduate"
        education_level: One of "Undergraduate", "Graduate", "High School", "Postdoctoral".
                         Leave empty to search all levels.
        field_of_study: e.g. "Computer Science", "Engineering", "Data Science".
                        Leave empty to search all fields.
        country: Country to restrict results to (default: "USA")

    Returns:
        List of up to 5 scholarship dicts with keys: name, provider, amount, deadline,
        field, level, apply_url.
        Returns empty list when APIFY_TOKEN env var is not set.
    """
    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        return []

    from apify_client import ApifyClient  # lazy import — only needed at call time

    client = ApifyClient(token)
    run_input: dict[str, Any] = {
        "searchQuery": keyword,
        "maxScholarships": _MAX_SCHOLARSHIPS,
        "country": country,
    }
    if education_level:
        run_input["educationLevel"] = education_level
    if field_of_study:
        run_input["fieldOfStudy"] = field_of_study

    # Use start() + wait_for_finish() instead of call() to avoid the SDK's
    # background log-streaming thread which times out on Windows (impit.TimeoutException).
    started = client.actor(_ACTOR_ID).start(run_input=run_input)
    if not started:
        return []
    run = client.run(started.id).wait_for_finish()
    if not run or not run.default_dataset_id:
        return []

    results: list[dict[str, Any]] = []
    for item in client.dataset(run.default_dataset_id).iterate_items():
        if len(results) >= _MAX_SCHOLARSHIPS:
            break
        if not results:
            log.debug("Apify scholarship raw item keys: %s", sorted(item.keys()))

        results.append({
            "name": _extract(item, "title", "name", "scholarshipName"),
            "provider": _extract(item, "provider", "source", "sponsor", "organization"),
            "amount": _extract(item, "amount", "award", "awardAmount", "value",
                               fallback="Not specified"),
            "deadline": _extract(item, "deadline", "closingDate", "dueDate",
                                 fallback=""),
            "field": _extract(item, "field_of_study", "fieldOfStudy", "major",
                              fallback="Any"),
            "level": _extract(item, "level", "educationLevel", "academicLevel",
                              fallback="Any"),
            "apply_url": _extract(item, "url", "applyUrl", "link", "scholarshipUrl"),
        })

    return results
