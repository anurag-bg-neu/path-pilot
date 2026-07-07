"""Apify jobs scraper — three dedicated actor runs in parallel.

  1. LinkedIn  — curious_coder/linkedin-jobs-scraper   → 10 results
  2. Indeed    — kaix/indeed-scraper                   → up to 100 results
  3. Others    — agentx/all-jobs-scraper
                 (Glassdoor, ZipRecruiter, Jobright)    →  5 results

Note: Y Combinator (jobs.ycombinator.com) is not a supported platform in
agentx/all-jobs-scraper. Jobright is used as the nearest AI-curated equivalent.
"""
import json
import logging
import os
import pathlib
import re
from typing import Any
from urllib.parse import quote_plus

_SEED_PATH = pathlib.Path(__file__).parent.parent.parent / "data" / "opportunities_seed.json"
_JOB_TYPES = {"internship", "role", "job"}


def _seed_jobs_fallback(keyword: str) -> list[dict[str, Any]]:
    """Return job/internship/role entries from the MCP seed dataset.

    Called when APIFY_TOKEN is not set — returns the same data the MCP server
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
    results = []
    for opp in opps:
        if opp.get("type", "").lower() not in _JOB_TYPES:
            continue
        title = opp.get("title", "").lower()
        field = opp.get("field", "").lower()
        if kw_words and not any(w in title or w in field for w in kw_words):
            continue
        amt = opp.get("amount_usd")
        results.append({
            "name": opp.get("title", ""),
            "company": "🗄️ Curated (MCP seed data)",
            "location": "Various",
            "salary": f"USD {amt:,}/yr" if amt else "—",
            "source_url": opp.get("source_url", ""),
            "closing_date": opp.get("deadline", ""),
            "source": "seed",
        })
    return results

_LINKEDIN_ACTOR_ID = "curious_coder/linkedin-jobs-scraper"
_INDEED_ACTOR_ID   = "kaix/indeed-scraper"
_ALL_JOBS_ACTOR_ID = "agentx/all-jobs-scraper"

_LINKEDIN_COUNT = 10
_INDEED_COUNT   = 100  # kaix supports up to 1000; cap at 100

# 3 platforms × 5 scraped each = 15 fetched, 10 kept.
_SECONDARY_PLATFORMS = ["Glassdoor", "ZipRecruiter", "Jobright"]
_SECONDARY_FETCH = 15  # total max_results sent to agentx actor
_SECONDARY_COUNT = 10  # results we return

_MAX_RETURN = _LINKEDIN_COUNT + _INDEED_COUNT + _SECONDARY_COUNT  # 120

# FAANG keyword suffix — appended to queries for LinkedIn, Indeed, and agentx when faang_only=True.
# Parentheses are required: without them, Indeed treats each company as an independent OR branch
# and ignores the role keywords entirely, collapsing 100 results → 2.
# MUST be wrapped in parentheses — without them Indeed mis-parses the OR operators
# and returns near-zero results (matches each company name independently of the role).
_FAANG_KW_SUFFIX = (
    "(Google OR Amazon OR Microsoft OR Meta OR Apple OR Netflix OR Nvidia "
    "OR Salesforce OR Adobe OR Uber OR Airbnb OR Stripe OR OpenAI OR Anthropic)"
)

log = logging.getLogger(__name__)

# Abbreviations that job boards don't recognise — expand them so actor queries match real postings.
_ABBREV = [
    (r'\bSDE\b',  'Software Development Engineer'),
    (r'\bSWE\b',  'Software Engineer'),
    (r'\bMLE\b',  'Machine Learning Engineer'),
    (r'\bDS\b',   'Data Scientist'),
    (r'\bPM\b',   'Product Manager'),
    (r'\bTPM\b',  'Technical Program Manager'),
]

def _expand(keyword: str) -> str:
    for pattern, replacement in _ABBREV:
        keyword = re.sub(pattern, replacement, keyword, flags=re.IGNORECASE)
    return keyword


# ── LinkedIn helpers ────────────────────────────────────────────────────────────

def _linkedin_url(keyword: str, location: str, remote_only: bool, faang_only: bool = False) -> str:
    # For FAANG mode, append company names to the keyword instead of using f_C= company-ID
    # filter. f_C= requires a fresh proxy IP per run — after the first run in a session
    # LinkedIn blocks the actor's proxy pool and returns 0. Keyword-based FAANG matching
    # is less precise but survives proxy reuse.
    kw = f"{keyword} {_FAANG_KW_SUFFIX}" if faang_only else keyword
    params = f"keywords={quote_plus(kw)}"
    if location:
        params += f"&location={quote_plus(location)}"
    if remote_only:
        params += "&f_WT=2"
    return f"https://www.linkedin.com/jobs/search/?{params}"


def _map_linkedin_item(item: dict[str, Any]) -> dict[str, Any]:
    salary_parts = item.get("salaryInfo") or []
    salary = ", ".join(str(s) for s in salary_parts) if salary_parts else "Not specified"
    posted = item.get("postedAt") or ""
    return {
        "name": item.get("title", ""),
        "company": item.get("companyName") or "Not provided",
        "location": item.get("location") or "",
        "salary": salary,
        "source_url": item.get("applyUrl") or item.get("link", ""),
        "closing_date": posted[:10] if posted else "",
        "source": "linkedin",
    }


# ── Indeed (kaix) helpers ───────────────────────────────────────────────────────

def _map_indeed_item(item: dict[str, Any]) -> dict[str, Any]:
    # kaix uses nested objects: title.text, company.name, location.city/state,
    # salary.min/max/currency/period, urls.apply / urls.indeed, dates.posted
    title_obj   = item.get("title") or {}
    name        = (title_obj.get("text") if isinstance(title_obj, dict) else None) or item.get("title", "")

    company_obj = item.get("company") or {}
    company     = (company_obj.get("name") if isinstance(company_obj, dict) else None) or "Not provided"

    loc_obj  = item.get("location") or {}
    if isinstance(loc_obj, dict):
        city  = loc_obj.get("city") or ""
        state = loc_obj.get("state") or ""
        loc_str = ", ".join(p for p in [city, state] if p)
    else:
        loc_str = str(loc_obj) if loc_obj else ""

    sal = item.get("salary") or {}
    if isinstance(sal, dict) and (sal.get("min") or sal.get("max")):
        lo       = sal.get("min")
        hi       = sal.get("max")
        currency = sal.get("currency") or "USD"
        period   = sal.get("period") or ""
        rng      = f"{int(lo):,}–{int(hi):,}" if lo and hi else (f"{int(lo):,}+" if lo else f"up to {int(hi):,}")
        salary   = f"{currency} {rng}/{period}" if period else f"{currency} {rng}"
    else:
        salary = "Not specified"

    urls_obj = item.get("urls") or {}
    source_url = (urls_obj.get("apply") or urls_obj.get("indeed")) if isinstance(urls_obj, dict) else ""

    dates_obj = item.get("dates") or {}
    posted    = (dates_obj.get("posted") if isinstance(dates_obj, dict) else None) or ""

    return {
        "name":         name,
        "company":      company,
        "location":     loc_str,
        "salary":       salary,
        "source_url":   source_url or "",
        "closing_date": posted[:10] if posted else "",
        "source":       "indeed",
    }


# ── agentx (Glassdoor / ZipRecruiter / Jobright) helpers ───────────────────────

def _agentx_salary(item: dict[str, Any]) -> str:
    lo = item.get("salary_minimum")
    hi = item.get("salary_maximum")
    currency = item.get("salary_currency") or "USD"
    period = item.get("salary_period") or ""
    if lo and hi:
        range_str = f"{int(lo):,}–{int(hi):,}"
    elif lo:
        range_str = f"{int(lo):,}+"
    elif hi:
        range_str = f"up to {int(hi):,}"
    else:
        return "Not specified"
    return f"{currency} {range_str}/{period}" if period else f"{currency} {range_str}"


def _agentx_location(item: dict[str, Any], fallback: str) -> str:
    loc = item.get("location")
    if isinstance(loc, dict):
        return loc.get("raw") or loc.get("locality") or fallback
    if isinstance(loc, str) and loc.strip():
        return loc.strip()
    return fallback


def _map_agentx_item(item: dict[str, Any], loc_fallback: str) -> dict[str, Any]:
    posted = item.get("posted_date") or ""
    return {
        "name": item.get("title", ""),
        "company": item.get("company_name") or "Not provided",
        "location": _agentx_location(item, loc_fallback),
        "salary": _agentx_salary(item),
        "source_url": item.get("official_url") or item.get("platform_url", ""),
        "closing_date": posted[:10] if posted else "",
        "source": (item.get("platform") or "other").lower(),
    }


# ── collect helpers ─────────────────────────────────────────────────────────────

def _collect_linkedin(client: Any, run_id: str, limit: int) -> list[dict[str, Any]]:
    run = client.run(run_id).wait_for_finish()
    if not run or not run.default_dataset_id:
        return []
    results = []
    for item in client.dataset(run.default_dataset_id).iterate_items():
        if not results:
            log.debug("LinkedIn raw keys: %s", sorted(item.keys()))
        results.append(_map_linkedin_item(item))
        if len(results) >= limit:
            break
    return results


def _collect_indeed(client: Any, run_id: str, limit: int) -> list[dict[str, Any]]:
    run = client.run(run_id).wait_for_finish()
    if not run or not run.default_dataset_id:
        return []
    results = []
    for item in client.dataset(run.default_dataset_id).iterate_items():
        if not results:
            log.debug("Indeed raw keys: %s", sorted(item.keys()))
        results.append(_map_indeed_item(item))
        if len(results) >= limit:
            break
    return results


def _collect_agentx(
    client: Any, run_id: str, limit: int, loc_fallback: str
) -> list[dict[str, Any]]:
    run = client.run(run_id).wait_for_finish()
    if not run or not run.default_dataset_id:
        return []
    results = []
    for item in client.dataset(run.default_dataset_id).iterate_items():
        if not results:
            log.debug("Agentx raw keys: %s", sorted(item.keys()))
        results.append(_map_agentx_item(item, loc_fallback))
        if len(results) >= limit:
            break
    return results


# ── public tool ─────────────────────────────────────────────────────────────────

def search_jobs_apify(
    queries: str,
    location: str = "",
    country: str = "United States",
    remote_only: bool = False,
    faang_only: bool = False,
) -> list[dict[str, Any]]:
    """Search live job listings across LinkedIn, Indeed, Glassdoor, ZipRecruiter, and Jobright.

    Three actor runs start in parallel then results are merged:
    - LinkedIn (curious_coder): 10 results
    - Indeed (kaix):            up to 100 results
    - Glassdoor + ZipRecruiter + Jobright (agentx): 5 results
    Total: up to 115 results.
    Call this AT MOST ONCE per user message.

    Args:
        queries: Job title or keywords, e.g. "software engineer internship"
        location: City/state e.g. "New York". Leave empty for nationwide.
        country: Full country name (default: "United States")
        remote_only: True to restrict results to remote-only positions
        faang_only: True to restrict to FAANG/Big Tech companies.
            LinkedIn uses company-ID filtering (reliable).
            Indeed/agentx append company names to keyword (best-effort).

    Returns:
        List of up to 115 job dicts: name, company, location, salary,
        source_url, closing_date, source.
        Falls back to the MCP seed dataset (each row tagged company="Curated
        (MCP seed data)") when APIFY_TOKEN is not set, actor startup fails,
        or the live scrape returns zero results.
    """
    token = os.getenv("APIFY_TOKEN", "")
    if not token:
        log.info("APIFY_TOKEN not set — returning MCP seed fallback for jobs.")
        return _seed_jobs_fallback(_expand(queries))

    # Expand abbreviations so all actors receive natural-language keywords that
    # match their search indexes (e.g. "SDE" → "Software Development Engineer").
    queries = _expand(queries)

    from apify_client import ApifyClient  # lazy import — only needed at call time

    client = ApifyClient(token)

    # ── 1. LinkedIn ─────────────────────────────────────────────────────────────
    li_url = _linkedin_url(queries, location, remote_only, faang_only)
    linkedin_started = client.actor(_LINKEDIN_ACTOR_ID).start(run_input={
        "urls": [li_url],
        "count": _LINKEDIN_COUNT,
        "scrapeCompany": False,
        "splitByLocation": False,
    })

    # ── 2. Indeed (kaix) ────────────────────────────────────────────────────────
    indeed_kw = f"{queries} {_FAANG_KW_SUFFIX}" if faang_only else queries
    indeed_input: dict[str, Any] = {
        "keyword":  indeed_kw,
        "location": location or "United States",
        "country":  "US",
        "maxItems": _INDEED_COUNT,
        "sort":     "relevance",
    }
    if remote_only:
        indeed_input["remote"] = "remote"

    indeed_started = client.actor(_INDEED_ACTOR_ID).start(run_input=indeed_input)

    # ── 3. Glassdoor + ZipRecruiter + Jobright ──────────────────────────────────
    agentx_kw = f"{queries} {_FAANG_KW_SUFFIX}" if faang_only else queries
    shared: dict[str, Any] = {
        "keyword": agentx_kw,
        "country": country,
        "remote_only": remote_only,
    }
    if location:
        shared["location"] = location

    secondary_started = client.actor(_ALL_JOBS_ACTOR_ID).start(run_input={
        **shared,
        "platforms": _SECONDARY_PLATFORMS,
        "max_results": _SECONDARY_FETCH,
    })

    if not linkedin_started or not indeed_started or not secondary_started:
        log.info("Apify job actors failed to start — returning MCP seed fallback for jobs.")
        return _seed_jobs_fallback(queries)

    loc_fallback = location or ("Remote" if remote_only else "")

    # Collect — each wait_for_finish() blocks until that run completes.
    linkedin_jobs  = _collect_linkedin(client, linkedin_started.id, _LINKEDIN_COUNT)
    indeed_jobs    = _collect_indeed(client, indeed_started.id, _INDEED_COUNT)
    secondary_jobs = _collect_agentx(client, secondary_started.id, _SECONDARY_COUNT, loc_fallback)

    raw = linkedin_jobs + indeed_jobs + secondary_jobs

    # Deduplicate by source URL — each URL is a unique posting.
    # Do NOT dedup by (title, company): FAANG companies post many roles with the
    # same generic title (e.g. "Software Engineer") for different teams; collapsing
    # them by title+company reduces 15+ real openings to 1–2.
    seen: dict[str, dict[str, Any]] = {}
    for job in raw:
        url = job.get("source_url", "").strip()
        if url:
            seen.setdefault(url, job)
        else:
            # No URL — use title+company as fallback key to avoid true duplicates
            key = f"{job.get('name','').lower().strip()}|{job.get('company','').lower().strip()}"
            seen.setdefault(key, job)

    live_results = list(seen.values())[:_MAX_RETURN]
    if not live_results:
        log.info("Live job scrape returned zero results — returning MCP seed fallback for jobs.")
        return _seed_jobs_fallback(queries)
    return live_results
