"""Apify scholarship scraper tool: live scholarships via majestic_fund/the-scholarship-scraper-actor.

Falls back to the MCP seed dataset (data/opportunities_seed.json) when APIFY_TOKEN is not set,
returning the same scholarship/grant rows the FastMCP server (tools/opportunities_mcp.py) exposes.
"""
import json
import logging
import os
import pathlib
from typing import Any

_ACTOR_ID = "majestic_fund/the-scholarship-scraper-actor"
_SEED_PATH = pathlib.Path(__file__).parent.parent.parent / "data" / "opportunities_seed.json"
_SCHOLARSHIP_TYPES = {"scholarship", "grant", "fellowship"}

# Hard guardrail: sent to the actor AND used as a post-cap.
# Never increase this without explicit human approval; each result consumes Apify credits.
_MAX_SCHOLARSHIPS = 5

log = logging.getLogger(__name__)


def _extract(item: dict[str, Any], *keys: str, fallback: str = "") -> str:
    """Return the first non-empty value found among the given keys."""
    for key in keys:
        val = item.get(key)
        if val and str(val).strip() not in ("", "None", "null", "N/A", "n/a"):
            return str(val).strip()
    return fallback


def _seed_scholarships_fallback(
    keyword: str,
    education_level: str,
    field_of_study: str,
) -> list[dict[str, Any]]:
    """Return scholarship/grant entries from the MCP seed dataset.

    Called when APIFY_TOKEN is not set; returns the same data the MCP server
    (tools/opportunities_mcp.py) exposes, labelled so the user knows it is curated
    fallback data and not live-scraped results.
    """
    try:
        with _SEED_PATH.open(encoding="utf-8") as fh:
            opps = json.load(fh)["opportunities"]
    except Exception:
        return []
    # Word-overlap match, not whole-phrase substring: a multi-word keyword like
    # "computer science graduate student" will never appear verbatim in a seed
    # title/field, so require only that at least one significant word overlaps.
    kw_words = [w for w in keyword.lower().split() if len(w) > 2]
    level_q = education_level.lower() if education_level else ""
    field_q = field_of_study.lower() if field_of_study else ""
    results = []
    for opp in opps:
        if opp.get("type", "").lower() not in _SCHOLARSHIP_TYPES:
            continue
        title = opp.get("title", "").lower()
        field = opp.get("field", "").lower()
        level = opp.get("level", "").lower()
        if kw_words and not any(w in title or w in field for w in kw_words):
            continue
        if level_q and level not in ("any", "") and level_q not in level:
            continue
        if field_q and field not in ("any", "") and field_q not in field:
            continue
        amt = opp.get("amount_usd")
        results.append({
            "name": opp.get("title", ""),
            "provider": "🗄️ Curated (MCP seed data)",
            "amount": f"USD {amt:,}" if amt else "-",
            "deadline": opp.get("deadline", ""),
            "field": opp.get("field", "Any"),
            "level": opp.get("level", "Any"),
            "apply_url": opp.get("source_url", ""),
        })
        if len(results) >= _MAX_SCHOLARSHIPS:
            break
    return results


def search_scholarships_apify(
    keyword: str,
    education_level: str = "",
    field_of_study: str = "",
    country: str = "USA",
) -> list[dict[str, Any]]:
    """Search live scholarships from Scholarships.com, Fastweb, and College Board via Apify.

    Falls back to the MCP seed dataset when APIFY_TOKEN is not set, actor startup
    fails, or the live scrape returns zero results.

    IMPORTANT: only call this tool when the user explicitly asks for scholarships,
    grants, or financial aid. Do NOT call it for job searches.
    Call this AT MOST ONCE per user message. Returns at most 5 scholarships.

    Args:
        keyword: Search terms, e.g. "computer science graduate" or "STEM international student F-1"
        education_level: One of "Undergraduate", "Graduate", "High School", "Postdoctoral".
                         Leave empty to search all levels.
        field_of_study: e.g. "Computer Science", "Engineering", "Data Science".
                        Leave empty to search all fields.
        country: Country to restrict results to (default: "USA")

    Returns:
        List of up to 5 scholarship dicts with keys: name, provider, amount, deadline,
        field, level, apply_url.
    """
    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        log.info("APIFY_TOKEN not set; returning MCP seed fallback for scholarships.")
        return _seed_scholarships_fallback(keyword, education_level, field_of_study)

    from apify_client import ApifyClient  # lazy import, only needed at call time

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
        log.info("Apify scholarship actor failed to start; returning MCP seed fallback.")
        return _seed_scholarships_fallback(keyword, education_level, field_of_study)
    run = client.run(started.id).wait_for_finish()
    if not run or not run.default_dataset_id:
        log.info("Apify scholarship run produced no dataset; returning MCP seed fallback.")
        return _seed_scholarships_fallback(keyword, education_level, field_of_study)

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

    if not results:
        log.info("Live scholarship scrape returned zero results; returning MCP seed fallback.")
        return _seed_scholarships_fallback(keyword, education_level, field_of_study)
    return results
