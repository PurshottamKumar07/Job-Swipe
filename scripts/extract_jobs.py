"""
Job Extractor (Async)
=====================
Reads job URLs (from a JSON file or directly from the SQLite database)
and extracts structured job data using three strategies (in priority order):

  1. ATS API  — Greenhouse / Lever / Ashby public JSON APIs.
  2. JSON-LD  — JobPosting schema in <script type="application/ld+json">.
  3. HTML     — Heuristic meta / OpenGraph / heading fallback.

Normalizes extracted data:
  - Links back to `source_job_link_id`
  - Parses salary into `salary_min`, `salary_max`, `salary_currency`, `salary_period`
  - Automatically detects `is_remote` work status
  - Records lifecycle and freshness timestamps

Usage:
    python scripts/extract_jobs.py [--input FILE] [--output FILE] [--run ID] [--concurrency N]
"""

import os
import re
import sys
import json
import asyncio
import argparse
import aiohttp
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from dataclasses import dataclass, field, asdict

# Ensure project root is in sys.path for standalone script execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ExtractedJob:
    """Structured details extracted from a single job URL."""
    source_url: str
    source_job_link_id: int | None = None
    title:       str | None = None
    company:     str | None = None
    location:    str | None = None
    salary:      str | None = None
    salary_min:  float | None = None
    salary_max:  float | None = None
    salary_currency: str | None = None
    salary_period:   str | None = None
    job_type:    str | None = None      # full-time / part-time / contract
    is_remote:   bool = False
    description: str | None = None      # first ~500 chars
    apply_url:   str | None = None
    posted_at:   str | None = None
    extraction_method: str = "none"     # api | jsonld | html | failed
    extracted_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    first_seen_at: str | None = None
    last_seen_at:  str | None = None
    is_active:     bool = True


# ---------------------------------------------------------------------------
# Salary and Remote Parsing Utilities
# ---------------------------------------------------------------------------

_CURRENCY_SYMBOLS = {
    "C$": "CAD",
    "A$": "AUD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "$": "USD",  # Must be last — "$" is a substring of "C$" and "A$"
}


def parse_salary(text: str | None) -> tuple[float | None, float | None, str | None, str | None]:
    """
    Parse a salary string into (salary_min, salary_max, currency, period).

    Handles ranges ($130,000 - $145,000, 100k to 140k/yr, $50/hr, etc.)
    Strictly avoids false positives such as years of experience ('3 - 5 years'),
    dates ('2024-05-01'), or working hours ('20 - 30 hours per week').
    """
    if not text:
        return None, None, None, None

    text = text.strip()

    # Currency detection
    currency = None
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in text:
            currency = code
            break
    if not currency:
        m_curr = re.search(r"\b(USD|EUR|GBP|CAD|AUD|INR|CHF)\b", text, re.I)
        if m_curr:
            currency = m_curr.group(1).upper()

    # Period detection
    period = None
    lower = text.lower()
    if re.search(r"\b(hour|hourly|hr|/h|/hr)\b", lower):
        period = "hour"
    elif re.search(r"\b(month|monthly|mo|/mo)\b", lower):
        period = "month"
    elif re.search(r"\b(year|yearly|yr|annual|annually|annum|/yr|/year)\b", lower):
        period = "year"

    has_currency = currency is not None or any(s in text for s in ("$", "€", "£", "₹", "¥"))
    has_salary_kw = bool(re.search(r"\b(salary|compensation|pay|rate|base|stipend)\b", lower))

    def to_num(num_str: str, k_flag: str | None) -> float:
        clean = num_str.replace(",", "").strip()
        val = float(clean)
        if k_flag or ("k" in num_str.lower() and val < 1000):
            val *= 1000
        return val

    num_pattern = r"(?:\d{1,3}(?:,\d{3})+|\d+)"

    # Rate unit: requires slash, 'per', 'a', or words like 'hourly', 'annually', 'monthly'
    # This prevents matching '5 years of experience' or '30 hours per week'
    rate_unit_pattern = r"(?:\s*(?:/\s*|per\s+|a\s+)(hour|hr|year|yr|annum|annual|month|mo)|\s+\b(hourly|annually|monthly|yearly)\b)"
    non_salary_pattern = r"\s*\b(years?|yrs?|days?|weeks?|team|people|hours?\s+per\s+week)\b"

    # 1. Range match: e.g. $130,000 to $145,000 or $60,000 - $80,000 or $100k - $140k
    range_regex = re.compile(
        r"(?:([$€£₹]|C\$|A\$)\s*)?"
        r"(" + num_pattern + r"(?:\.\d+)?)\s*(k|K)?"
        r"\s*(?:-|–|—|to|\.\.\.)\s*"
        r"(?:([$€£₹]|C\$|A\$)\s*)?"
        r"(" + num_pattern + r"(?:\.\d+)?)\s*(k|K)?"
        r"(?:" + rate_unit_pattern + r")?"
        r"(?:" + non_salary_pattern + r")?",
        re.IGNORECASE,
    )

    for match in range_regex.finditer(text):
        c1, n1, k1, c2, n2, k2, u1, u2, non_salary_unit = match.groups()

        # Reject if followed by years/days/weeks/etc. (e.g. "3 - 5 years of experience")
        if non_salary_unit:
            continue

        unit = u1 or u2
        is_explicit_currency = bool(c1 or c2 or (currency and any(s in text for s in ("$", "€", "£", "₹", "¥"))))
        is_k_notation = bool(k1 or k2)

        # Non-salary text (like date "2024-05-01" or year range "2020 - 2024") must have currency or k or salary keyword
        if not (is_explicit_currency or is_k_notation or unit or has_salary_kw):
            continue

        try:
            v1 = to_num(n1, k1)
            v2 = to_num(n2, k2)

            # Avoid date patterns like 2024-05
            if not is_explicit_currency and not is_k_notation and not unit:
                if (1990 <= v1 <= 2040 and 1 <= v2 <= 31) or (1990 <= v2 <= 2040 and 1 <= v1 <= 31):
                    continue

            val_min = min(v1, v2)
            val_max = max(v1, v2)

            if val_min < 10 and not unit and not (is_explicit_currency and period == "hour"):
                continue

            match_period = period
            if unit:
                u_low = unit.lower()
                if "hour" in u_low or "hr" in u_low:
                    match_period = "hour"
                elif "month" in u_low or "mo" in u_low:
                    match_period = "month"
                elif "year" in u_low or "yr" in u_low or "ann" in u_low:
                    match_period = "year"

            if not match_period:
                if val_min >= 20000:
                    match_period = "year"
                elif val_min <= 250 and (period == "hour" or is_explicit_currency):
                    match_period = "hour"
                elif 1000 <= val_min < 20000:
                    match_period = "month"

            return val_min, val_max, currency or "USD", match_period or "year"
        except (ValueError, TypeError):
            continue

    # 2. Single value match: e.g. $120,000/year or $65/hr or $150k
    single_regex = re.compile(
        r"(?:([$€£₹]|C\$|A\$)\s*)?"
        r"(" + num_pattern + r"(?:\.\d+)?)\s*(k|K)?"
        r"(?:\s*(?:/\s*|per\s+)(hour|hr|hourly|year|yr|annum|annual|month|mo))?"
        r"(?:\s*(years?|yrs?|days?|weeks?|team|people))?",
        re.IGNORECASE,
    )

    for match in single_regex.finditer(text):
        c1, n1, k1, unit, non_salary_unit = match.groups()
        if non_salary_unit:
            continue

        is_explicit_currency = bool(c1 or has_currency)
        is_k = bool(k1)

        if not (c1 or (is_k and (has_salary_kw or unit)) or (has_salary_kw and unit)):
            continue

        try:
            val = to_num(n1, k1)
            if val < 10 and not unit:
                continue

            match_period = period
            if unit:
                u_low = unit.lower()
                if "hour" in u_low or "hr" in u_low:
                    match_period = "hour"
                elif "month" in u_low or "mo" in u_low:
                    match_period = "month"
                elif "year" in u_low or "yr" in u_low or "ann" in u_low:
                    match_period = "year"

            if not match_period:
                if val >= 20000:
                    match_period = "year"
                elif val <= 250 and (period == "hour" or c1):
                    match_period = "hour"
                elif 1000 <= val < 20000:
                    match_period = "month"

            return val, val, currency or "USD", match_period or "year"
        except (ValueError, TypeError):
            continue

    return None, None, currency, period


def detect_is_remote(
    title: str | None,
    location: str | None,
    description: str | None,
    source_url: str = "",
) -> bool:
    """Detect whether a job posting is remote."""
    full_text = " ".join([t for t in (location, title, description[:400] if description else None) if t])

    # Explicit negative check
    negative_pattern = re.compile(
        r"\b(not\s+remote|no\s+remote|non-remote|in-office\s+only|on-site\s+only|must\s+work\s+on-site)\b",
        re.I,
    )
    if full_text and negative_pattern.search(full_text):
        return False

    pattern = re.compile(
        r"\b(remote|wfh|work\s+from\s+home|telecommute|anywhere|distributed|virtual|remote-friendly)\b",
        re.I,
    )
    for text in (location, title):
        if text and pattern.search(text):
            return True

    if source_url and "remote" in source_url.lower():
        parsed_path = urlparse(source_url).path.lower()
        if not any(k in parsed_path for k in ("statistics", "policy", "calculator", "blog", "article")):
            return True

    if description and pattern.search(description[:300]):
        return True

    return False


# ---------------------------------------------------------------------------
# ATS detection & API extraction (async)
# ---------------------------------------------------------------------------

_ATS_PATTERNS = {
    "greenhouse": [
        re.compile(r"boards\.greenhouse\.io/(?:embed/job_board\?for=)?([^/?#&]+)", re.I),
        re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)", re.I),
    ],
    "lever": [
        re.compile(r"jobs\.lever\.co/([^/?#]+)", re.I),
    ],
    "ashby": [
        re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I),
    ],
}


def _detect_ats(url: str) -> tuple[str, str] | None:
    """Return (ats_name, company_slug) if URL belongs to a known ATS, else None."""
    parsed = urlparse(url)
    if "greenhouse.io" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "for" in qs and qs["for"]:
            return "greenhouse", qs["for"][0]

    for ats, patterns in _ATS_PATTERNS.items():
        for pat in patterns:
            m = pat.search(url)
            if m:
                slug = m.group(1).strip()
                if slug and slug.lower() not in ("embed", "jobs", "job", "api", "v1"):
                    return ats, slug
    return None


async def _fetch_greenhouse(company: str, session: aiohttp.ClientSession) -> list[ExtractedJob]:
    api = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
    try:
        async with session.get(api) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            jobs = []
            for j in data.get("jobs", []):
                title = j.get("title")
                loc = ", ".join(loc.get("name", "") for loc in j.get("offices", [])) or None
                desc = _trim(j.get("content", ""))
                url = j.get("absolute_url", "")
                s_min, s_max, s_curr, s_per = parse_salary(desc)
                is_rem = detect_is_remote(title, loc, desc, url)

                jobs.append(ExtractedJob(
                    source_url=url,
                    title=title,
                    company=company,
                    location=loc,
                    description=desc,
                    salary_min=s_min,
                    salary_max=s_max,
                    salary_currency=s_curr,
                    salary_period=s_per,
                    is_remote=is_rem,
                    apply_url=url,
                    posted_at=j.get("updated_at"),
                    extraction_method="api:greenhouse",
                ))
            return jobs
    except Exception:
        return []


async def _fetch_lever(company: str, session: aiohttp.ClientSession) -> list[ExtractedJob]:
    api = f"https://api.lever.co/v0/postings/{company}?mode=json"
    try:
        async with session.get(api) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            jobs = []
            for j in data:
                title = j.get("text")
                loc = j.get("categories", {}).get("location")
                desc = _trim(j.get("descriptionPlain", ""))
                url = j.get("hostedUrl", "")
                s_min, s_max, s_curr, s_per = parse_salary(desc)
                is_rem = detect_is_remote(title, loc, desc, url)

                jobs.append(ExtractedJob(
                    source_url=url,
                    title=title,
                    company=company,
                    location=loc,
                    job_type=j.get("categories", {}).get("commitment"),
                    description=desc,
                    salary_min=s_min,
                    salary_max=s_max,
                    salary_currency=s_curr,
                    salary_period=s_per,
                    is_remote=is_rem,
                    apply_url=j.get("applyUrl"),
                    posted_at=_epoch_to_iso(j.get("createdAt")),
                    extraction_method="api:lever",
                ))
            return jobs
    except Exception:
        return []


async def _fetch_ashby(company: str, session: aiohttp.ClientSession) -> list[ExtractedJob]:
    api = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    try:
        async with session.get(api) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
            jobs = []
            for j in data.get("jobs", []):
                title = j.get("title")
                loc = j.get("location")
                desc = _trim(j.get("descriptionPlain", ""))
                url = j.get("jobUrl", "")
                s_min, s_max, s_curr, s_per = parse_salary(desc)
                is_rem = detect_is_remote(title, loc, desc, url)

                jobs.append(ExtractedJob(
                    source_url=url,
                    title=title,
                    company=data.get("organizationName", company),
                    location=loc,
                    job_type=j.get("employmentType"),
                    description=desc,
                    salary_min=s_min,
                    salary_max=s_max,
                    salary_currency=s_curr,
                    salary_period=s_per,
                    is_remote=is_rem,
                    apply_url=j.get("applyUrl") or url,
                    posted_at=j.get("publishedAt"),
                    extraction_method="api:ashby",
                ))
            return jobs
    except Exception:
        return []


_ATS_FETCHERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
}


# ---------------------------------------------------------------------------
# JSON-LD extraction
# ---------------------------------------------------------------------------

def _collect_jsonld_nodes(data) -> list[dict]:
    """Recursively collect all JSON-LD object dictionaries, including from @graph."""
    nodes = []
    if isinstance(data, list):
        for item in data:
            nodes.extend(_collect_jsonld_nodes(item))
    elif isinstance(data, dict):
        if "@graph" in data and isinstance(data["@graph"], list):
            nodes.extend(_collect_jsonld_nodes(data["@graph"]))
        else:
            nodes.append(data)
    return nodes


def _extract_jsonld(html: str, source_url: str) -> ExtractedJob | None:
    """Look for JobPosting structured data in <script type="application/ld+json"> blocks."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        text = (script.string or "").strip()
        if not text:
            continue

        if text.startswith("<![CDATA[") and text.endswith("]]>"):
            text = text[9:-3].strip()
        elif text.startswith("/*") and text.endswith("*/"):
            text = text[2:-2].strip()

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue

        nodes = _collect_jsonld_nodes(data)
        for node in nodes:
            if not isinstance(node, dict):
                continue
            raw_type = node.get("@type", "")
            types = [t.lower() for t in raw_type] if isinstance(raw_type, list) else [str(raw_type).lower()]
            if "jobposting" in types:
                title = node.get("title")
                company = _nested_name(node.get("hiringOrganization"))
                loc = _nested_name(node.get("jobLocation"))
                job_loc_type = node.get("jobLocationType")
                if not loc and job_loc_type:
                    loc = str(job_loc_type)
                desc = _trim(node.get("description", ""))

                # Salary extraction from JSON-LD
                salary = None
                s_min = None
                s_max = None
                s_curr = None
                s_per = None

                sal_data = node.get("baseSalary")
                if isinstance(sal_data, dict):
                    curr = sal_data.get("currency") or "USD"
                    val = sal_data.get("value")
                    if isinstance(val, dict):
                        unit = val.get("unitText", "")
                        if "minValue" in val or "maxValue" in val:
                            try:
                                if val.get("minValue") is not None:
                                    s_min = float(val["minValue"])
                                if val.get("maxValue") is not None:
                                    s_max = float(val["maxValue"])
                                if s_min is not None and s_max is None:
                                    s_max = s_min
                                elif s_max is not None and s_min is None:
                                    s_min = s_max
                            except (ValueError, TypeError):
                                pass
                        elif "value" in val:
                            try:
                                s_min = float(val["value"])
                                s_max = s_min
                            except (ValueError, TypeError):
                                pass

                        s_curr = curr
                        if unit:
                            u_low = str(unit).lower()
                            s_per = "hour" if "hour" in u_low else "month" if "month" in u_low else "year"
                        elif s_min:
                            s_per = "year" if s_min >= 20000 else "hour" if s_min <= 250 else "month"

                        if s_min is not None and s_max is not None:
                            prefix = "$" if s_curr == "USD" else s_curr + " "
                            if s_min == s_max:
                                salary = f"{prefix}{s_min:,.0f}/{s_per or 'year'}"
                            else:
                                salary = f"{prefix}{s_min:,.0f} - {prefix}{s_max:,.0f}/{s_per or 'year'}"
                    elif isinstance(val, (int, float)):
                        s_min = float(val)
                        s_max = float(val)
                        s_curr = curr
                        s_per = "year" if s_min >= 20000 else "hour" if s_min <= 250 else "month"
                        prefix = "$" if s_curr == "USD" else s_curr + " "
                        salary = f"{prefix}{s_min:,.0f}/{s_per}"
                    elif isinstance(val, str):
                        s_min, s_max, s_curr, s_per = parse_salary(val)
                        salary = val
                elif isinstance(sal_data, (str, int, float)):
                    s_min, s_max, s_curr, s_per = parse_salary(str(sal_data))
                    salary = str(sal_data)

                # Fallback to description for salary
                if s_min is None and desc:
                    s_min, s_max, s_curr, s_per = parse_salary(desc)
                    if s_min is not None:
                        curr_prefix = "$" if s_curr == "USD" else (s_curr or "$")
                        salary = f"{curr_prefix}{s_min:,.0f}" + (f" - {curr_prefix}{s_max:,.0f}" if s_max and s_max != s_min else "") + (f"/{s_per}" if s_per else "")

                # Remote detection
                is_rem = False
                if str(job_loc_type).upper() == "TELECOMMUTE":
                    is_rem = True
                elif node.get("applicantLocationRequirements"):
                    is_rem = True
                else:
                    is_rem = detect_is_remote(title, loc, desc, source_url)

                return ExtractedJob(
                    source_url=source_url,
                    title=title,
                    company=company,
                    location=loc,
                    salary=salary,
                    salary_min=s_min,
                    salary_max=s_max,
                    salary_currency=s_curr,
                    salary_period=s_per,
                    job_type=node.get("employmentType"),
                    is_remote=is_rem,
                    description=desc,
                    apply_url=node.get("url") or source_url,
                    posted_at=node.get("datePosted"),
                    extraction_method="jsonld",
                )
    return None


# ---------------------------------------------------------------------------
# HTML heuristic fallback
# ---------------------------------------------------------------------------

def _extract_html(html: str, source_url: str) -> ExtractedJob:
    """Best-effort extraction using BeautifulSoup meta / heading heuristics."""
    soup = BeautifulSoup(html, "html.parser")

    title = (
        _og(soup, "og:title")
        or _og(soup, "twitter:title")
        or _meta(soup, "twitter:title")
        or (soup.title.get_text(strip=True) if soup.title else None)
        or _first_text(soup, ["h1", "h2"])
    )
    company = (
        _og(soup, "og:site_name")
        or _meta(soup, "author")
        or urlparse(source_url).netloc.lower().removeprefix("www.")
    )
    description = (
        _og(soup, "og:description")
        or _og(soup, "twitter:description")
        or _meta(soup, "description")
    )
    desc_clean = _trim(description or "")

    # Parse salary from description
    s_min, s_max, s_curr, s_per = parse_salary(desc_clean)
    raw_salary = None
    if s_min is not None:
        curr_prefix = "$" if s_curr == "USD" else (s_curr or "$")
        if s_max and s_max != s_min:
            raw_salary = f"{curr_prefix}{s_min:,.0f} - {curr_prefix}{s_max:,.0f}"
        else:
            raw_salary = f"{curr_prefix}{s_min:,.0f}"
        if s_per:
            raw_salary += f"/{s_per}"

    is_rem = detect_is_remote(title, None, desc_clean, source_url)

    return ExtractedJob(
        source_url=source_url,
        title=title,
        company=company,
        description=desc_clean,
        salary=raw_salary,
        salary_min=s_min,
        salary_max=s_max,
        salary_currency=s_curr,
        salary_period=s_per,
        is_remote=is_rem,
        apply_url=source_url,
        extraction_method="html",
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _trim(text: str, max_chars: int = 500) -> str | None:
    if not text:
        return None
    text = BeautifulSoup(text, "html.parser").get_text(separator=" ", strip=True)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _nested_name(obj) -> str | None:
    if isinstance(obj, str):
        return obj.strip() or None
    if isinstance(obj, dict):
        if "address" in obj:
            addr = obj["address"]
            if isinstance(addr, str):
                return addr.strip() or None
            if isinstance(addr, dict):
                parts = [
                    addr.get("addressLocality"),
                    addr.get("addressRegion"),
                    addr.get("addressCountry"),
                ]
                parts = [p.strip() for p in parts if isinstance(p, str) and p.strip()]
                if parts:
                    return ", ".join(parts)
        if obj.get("name"):
            return str(obj["name"]).strip()
        if obj.get("addressLocality"):
            return str(obj["addressLocality"]).strip()
    if isinstance(obj, list) and obj:
        return _nested_name(obj[0])
    return None


def _og(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
    return tag["content"].strip() if tag and tag.get("content") else None


def _meta(soup: BeautifulSoup, name: str) -> str | None:
    tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", property=name)
    return tag["content"].strip() if tag and tag.get("content") else None


def _first_text(soup: BeautifulSoup, tags: list[str]) -> str | None:
    for tag in tags:
        el = soup.find(tag)
        if el:
            t = el.get_text(strip=True)
            if t:
                return t
    return None


def _epoch_to_iso(ms) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> str | None:
    try:
        async with session.get(url, allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if resp.status == 200 and ("text/html" in content_type or "application/xhtml+xml" in content_type):
                return await resp.text(errors="replace")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Async extractor class
# ---------------------------------------------------------------------------

class JobExtractor:
    def __init__(
        self,
        delay: float = 0.5,
        timeout: int = 10,
        concurrency: int = 10,
        db: Database | None = None,
    ):
        self.delay = delay
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.concurrency = concurrency
        self.db = db or Database()
        self._run_id: int | None = None
        self._lock = asyncio.Lock()

    async def extract_from_run(self, crawl_run_id: int, run_id: int | None = None) -> list[ExtractedJob]:
        """Extract structured job data directly from all links belonging to a crawl run."""
        links = self.db.get_job_links(crawl_run_id=crawl_run_id, limit=10000)
        total = len(links)
        if total == 0:
            return []

        if run_id is not None:
            self._run_id = run_id
        else:
            self._run_id = self.db.create_crawl_run(run_type="extract", max_pages=total)

        print(f"\n{'=' * 60}")
        print(f"  Job Extractor  (run #{self._run_id} from crawl #{crawl_run_id})")
        print(f"  Job Links   : {total}")
        print(f"  Concurrency : {self.concurrency}")
        print(f"  Database    : {self.db.db_path}")
        print(f"{'=' * 60}\n")

        results: list[ExtractedJob] = []
        fetched_ats: set[str] = set()
        semaphore = asyncio.Semaphore(self.concurrency)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; JobExtractor/1.0; "
                "+https://github.com/example/jobcrawler)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers=headers,
        ) as session:
            tasks = []
            for i, link in enumerate(links, 1):
                url = link.get("url", "")
                link_id = link.get("id")
                task = asyncio.create_task(
                    self._extract_worker(
                        session, semaphore, url, i, total, fetched_ats, results,
                        source_job_link_id=link_id,
                    )
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

        self.db.finish_crawl_run(
            self._run_id,
            pages_crawled=len(results),
            links_inspected=total,
            status="completed",
        )
        return results

    async def extract_from_file(self, input_path: str) -> list[ExtractedJob]:
        """Extract structured job data from a job_links.json file."""
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        job_links = data.get("job_links", [])
        total = len(job_links)

        self._run_id = self.db.create_crawl_run(run_type="extract", max_pages=total)

        print(f"\n{'=' * 60}")
        print(f"  Job Extractor  (run #{self._run_id})")
        print(f"  Input       : {input_path}")
        print(f"  URLs        : {total}")
        print(f"  Concurrency : {self.concurrency}")
        print(f"  Database    : {self.db.db_path}")
        print(f"{'=' * 60}\n")

        results: list[ExtractedJob] = []
        fetched_ats: set[str] = set()
        semaphore = asyncio.Semaphore(self.concurrency)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; JobExtractor/1.0; "
                "+https://github.com/example/jobcrawler)"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers=headers,
        ) as session:
            tasks = []
            for i, link in enumerate(job_links, 1):
                url = link.get("url", "")
                link_id = link.get("id")
                task = asyncio.create_task(
                    self._extract_worker(
                        session, semaphore, url, i, total, fetched_ats, results,
                        source_job_link_id=link_id,
                    )
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

        self.db.finish_crawl_run(
            self._run_id,
            pages_crawled=len(results),
            links_inspected=total,
            status="completed",
        )
        return results

    async def _extract_worker(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        url: str,
        index: int,
        total: int,
        fetched_ats: set[str],
        results: list[ExtractedJob],
        source_job_link_id: int | None = None,
    ) -> None:
        async with semaphore:
            print(f"[{index:>3}/{total}]  {url}")

            # Automatically resolve source_job_link_id if not explicitly provided
            if source_job_link_id is None:
                source_job_link_id = self.db.get_job_link_id_by_url(url)

            extracted = await self._extract_one(url, fetched_ats, session)

            async with self._lock:
                if extracted is None:
                    print(f"        -> [failed]")
                    failed_job = ExtractedJob(
                        source_url=url,
                        source_job_link_id=source_job_link_id,
                        extraction_method="failed",
                    )
                    results.append(failed_job)
                    self.db.insert_extracted_job_from_dataclass(
                        failed_job,
                        crawl_run_id=self._run_id,
                        source_job_link_id=source_job_link_id,
                    )
                elif isinstance(extracted, list):
                    print(f"        -> API: {len(extracted)} jobs")
                    results.extend(extracted)
                    for ej in extracted:
                        ej.source_job_link_id = source_job_link_id
                        self.db.insert_extracted_job_from_dataclass(
                            ej,
                            crawl_run_id=self._run_id,
                            source_job_link_id=source_job_link_id,
                        )
                else:
                    print(f"        -> [{extracted.extraction_method}] {extracted.title or '(no title)'}")
                    extracted.source_job_link_id = source_job_link_id
                    results.append(extracted)
                    self.db.insert_extracted_job_from_dataclass(
                        extracted,
                        crawl_run_id=self._run_id,
                        source_job_link_id=source_job_link_id,
                    )

    async def _extract_one(
        self,
        url: str,
        fetched_ats: set[str],
        session: aiohttp.ClientSession,
    ) -> list[ExtractedJob] | ExtractedJob | None:

        # 1. ATS API
        ats_match = _detect_ats(url)
        if ats_match:
            ats_name, company = ats_match
            cache_key = f"{ats_name}:{company}"
            already_fetched = False
            async with self._lock:
                if cache_key in fetched_ats:
                    already_fetched = True
            if not already_fetched:
                fetcher = _ATS_FETCHERS.get(ats_name)
                if fetcher:
                    jobs = await fetcher(company, session)
                    if jobs:
                        async with self._lock:
                            fetched_ats.add(cache_key)
                        return jobs

        # 2. Fetch HTML
        html = await _fetch_html(url, session)
        if not html:
            return None

        # 3. JSON-LD schema
        job = _extract_jsonld(html, url)
        if job:
            return job

        # 4. HTML heuristic fallback
        return _extract_html(html, url)

    def save(self, jobs: list[ExtractedJob], output_path: str) -> None:
        methods: dict[str, int] = {}
        for j in jobs:
            methods[j.extraction_method] = methods.get(j.extraction_method, 0) + 1

        output = {
            "extraction_metadata": {
                "total_jobs": len(jobs),
                "by_method": methods,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "jobs": [asdict(j) for j in jobs],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 60}")
        print(f"  Extraction complete")
        print(f"{'=' * 60}")
        print(f"  Total extracted : {len(jobs)}")
        for method, count in sorted(methods.items()):
            print(f"    {method:<22} : {count}")
        print(f"  Saved to        : {output_path}")
        print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Extract structured job data from URLs in a job_links.json file or DB run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i",
        default="job_links.json",
        help="Input JSON from crwl.py (default: job_links.json).",
    )
    parser.add_argument(
        "--run", "-r",
        type=int,
        default=None,
        help="Crawl run ID to extract links from directly in the database.",
    )
    parser.add_argument(
        "--output", "-o",
        default="extracted_jobs.json",
        help="Output JSON file (default: extracted_jobs.json).",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5).",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=10,
        help="Request timeout in seconds (default: 10).",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=10,
        help="Maximum concurrent requests (default: 10).",
    )

    args = parser.parse_args()
    extractor = JobExtractor(
        delay=args.delay,
        timeout=args.timeout,
        concurrency=args.concurrency,
    )

    if args.run:
        jobs = asyncio.run(extractor.extract_from_run(args.run))
    else:
        jobs = asyncio.run(extractor.extract_from_file(args.input))

    extractor.save(jobs, args.output)


if __name__ == "__main__":
    main()
