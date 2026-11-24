"""
Free Jobs API Fetcher
=====================
Fetches job listings from two completely free, keyless APIs and saves them
directly to the SQLite database using the same `extracted_jobs` table as
the scraper — the frontend works with zero changes.

Sources:
  • Remotive  — https://remotive.com/api/remote-jobs  (global remote tech jobs)
  • Himalayas — https://himalayas.app/jobs/api        (global remote, salary data)

No API key, no signup, no credit card required.

Usage (CLI):
    python scripts/free_jobs.py --source remotive
    python scripts/free_jobs.py --source himalayas --search "python developer"
    python scripts/free_jobs.py --source all --search "software engineer"
    python scripts/free_jobs.py --source remotive --category software-dev --limit 100
"""

import os
import sys
import re
import asyncio
import argparse
import aiohttp
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# Ensure project root in path for standalone execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REMOTIVE_URL  = "https://remotive.com/api/remote-jobs"
HIMALAYAS_URL = "https://himalayas.app/jobs/api"

# Remotive job categories (pass to ?category=)
REMOTIVE_CATEGORIES = [
    "software-dev", "customer-service", "design", "devops",
    "finance", "hr", "marketing", "product", "qa", "sales",
    "data", "backend", "frontend", "fullstack", "mobile",
]

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; crwlr/1.0; job aggregator)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Main fetcher class
# ---------------------------------------------------------------------------

class FreeJobsFetcher:
    """
    Fetches from Remotive and/or Himalayas and upserts into the crwlr DB.
    Each fetch session is tracked as a crawl_run with run_type='api_fetch'.
    """

    def __init__(self, db: Database | None = None, concurrency: int = 3):
        self.db          = db or Database()
        self.concurrency = concurrency
        self._run_id: int | None = None

        self.fetched = 0
        self.saved   = 0
        self.errors  = 0

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def fetch_remotive(
        self,
        search:   str | None = None,
        category: str | None = None,
        limit:    int | None = None,
    ) -> list[dict]:
        """Fetch from Remotive API. Returns raw job dicts."""
        params: dict = {}
        if search:   params["search"]   = search
        if category: params["category"] = category
        if limit:    params["limit"]    = limit

        print(f"[remotive] Fetching — search={search!r}  category={category}  limit={limit}")

        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
            try:
                async with session.get(
                    REMOTIVE_URL, params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        print(f"[remotive] HTTP {resp.status}")
                        return []
                    data  = await resp.json(content_type=None)
                    jobs  = data.get("jobs", [])
                    print(f"[remotive] Got {len(jobs)} listings")
                    return jobs
            except Exception as exc:
                print(f"[remotive] Fetch error: {exc}")
                self.errors += 1
                return []

    async def fetch_himalayas(
        self,
        search: str | None = None,
        limit:  int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Fetch from Himalayas API. Returns raw job dicts."""
        params: dict = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search

        print(f"[himalayas] Fetching — search={search!r}  limit={limit}  offset={offset}")

        async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
            try:
                async with session.get(
                    HIMALAYAS_URL, params=params,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        print(f"[himalayas] HTTP {resp.status}")
                        return []
                    data = await resp.json(content_type=None)
                    jobs = data.get("jobs", [])
                    print(f"[himalayas] Got {len(jobs)} listings")
                    return jobs
            except Exception as exc:
                print(f"[himalayas] Fetch error: {exc}")
                self.errors += 1
                return []

    async def run(
        self,
        source:   str = "all",        # "remotive" | "himalayas" | "all"
        search:   str | None = None,
        category: str | None = None,  # Remotive only
        limit:    int = 100,
    ) -> int:
        """
        Main entry. Fetches from selected source(s), saves to DB.
        Returns number of jobs saved.
        """
        # Pre-create run if not already set by the API endpoint
        if self._run_id is None:
            self._run_id = self.db.create_crawl_run(
                run_type="api_fetch",
                seed_urls=[f"{source}:{search or 'all'}"],
            )

        all_jobs: list[tuple[str, dict]] = []  # (source_name, raw_job)

        if source in ("remotive", "all"):
            jobs = await self.fetch_remotive(search=search, category=category, limit=limit)
            all_jobs.extend(("remotive", j) for j in jobs)

        if source in ("himalayas", "all"):
            jobs = await self.fetch_himalayas(search=search, limit=limit)
            all_jobs.extend(("himalayas", j) for j in jobs)

        self.fetched = len(all_jobs)
        print(f"[free_jobs] Total fetched: {self.fetched} — saving to DB...")

        for src_name, job in all_jobs:
            self._save_job(src_name, job)

        self.db.finish_crawl_run(
            self._run_id,
            status="completed",
            pages_crawled=1,
            links_inspected=self.fetched,
            errors=self.errors,
        )
        print(f"[free_jobs] Done — saved {self.saved}  errors {self.errors}")
        return self.saved

    # ------------------------------------------------------------------
    # DB save helpers
    # ------------------------------------------------------------------

    def _save_job(self, source: str, job: dict) -> None:
        try:
            if source == "remotive":
                self._save_remotive(job)
            elif source == "himalayas":
                self._save_himalayas(job)
        except Exception as exc:
            print(f"[free_jobs] Save error ({source}): {exc}")
            self.errors += 1

    def _save_remotive(self, job: dict) -> None:
        """Map Remotive job dict → extracted_jobs schema."""
        source_url = job.get("url", "")
        if not source_url:
            return

        # Strip HTML from description
        raw_desc = job.get("description", "") or ""
        description = _strip_html(raw_desc)[:2000]

        # Salary — Remotive provides raw string like "$80k-$120k"
        salary_str = job.get("salary") or None
        salary_min, salary_max, salary_currency, salary_period = _parse_salary_string(salary_str)

        job_type_raw = job.get("job_type", "") or ""
        job_type = _map_job_type(job_type_raw)

        self.db.insert_extracted_job(
            source_url        = source_url,
            crawl_run_id      = self._run_id,
            title             = job.get("title"),
            company           = job.get("company_name"),
            location          = job.get("candidate_required_location") or "Remote",
            salary            = salary_str,
            salary_min        = salary_min,
            salary_max        = salary_max,
            salary_currency   = salary_currency,
            salary_period     = salary_period,
            job_type          = job_type,
            is_remote         = True,   # Remotive is 100% remote
            description       = description,
            apply_url         = source_url,
            posted_at         = job.get("publication_date"),
            extraction_method = "api",
        )
        self.saved += 1

    def _save_himalayas(self, job: dict) -> None:
        """Map Himalayas job dict → extracted_jobs schema."""
        source_url = job.get("applicationLink") or job.get("guid", "")
        if not source_url:
            return

        raw_desc = job.get("description", "") or ""
        description = _strip_html(raw_desc)[:2000]

        # Himalayas has explicit salary fields
        salary_min  = _safe_float(job.get("minSalary"))
        salary_max  = _safe_float(job.get("maxSalary"))
        currency    = job.get("currency") or ("USD" if (salary_min or salary_max) else None)
        period      = job.get("salaryPeriod") or ("year" if (salary_min or salary_max) else None)
        salary_str  = None
        if salary_min and salary_max:
            sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency or "", "")
            salary_str = f"{sym}{int(salary_min):,} – {sym}{int(salary_max):,} / {period or 'year'}"

        # Location: use locationRestrictions array → join as string
        loc_list = job.get("locationRestrictions") or []
        location = ", ".join(loc_list[:3]) if loc_list else "Remote"

        emp_type = job.get("employmentType") or ""
        job_type = _map_job_type(emp_type)

        # pubDate is a Unix timestamp
        pub_ts   = job.get("pubDate")
        posted_at = (
            datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat()
            if pub_ts else None
        )

        self.db.insert_extracted_job(
            source_url        = source_url,
            crawl_run_id      = self._run_id,
            title             = job.get("title"),
            company           = job.get("companyName"),
            location          = location,
            salary            = salary_str,
            salary_min        = salary_min,
            salary_max        = salary_max,
            salary_currency   = currency,
            salary_period     = period,
            job_type          = job_type,
            is_remote         = True,   # Himalayas is 100% remote
            description       = description,
            apply_url         = source_url,
            posted_at         = posted_at,
            extraction_method = "api",
        )
        self.saved += 1


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    try:
        text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _map_job_type(raw: str) -> str | None:
    r = raw.lower()
    if any(w in r for w in ("full", "permanent")):
        return "full-time"
    if "part" in r:
        return "part-time"
    if "contract" in r:
        return "contract"
    if "freelance" in r:
        return "freelance"
    if "intern" in r:
        return "internship"
    return None


_SALARY_RE = re.compile(
    r"[\$€£₹]?\s*(\d[\d,\.]*)\s*[kK]?\s*[-–to]+\s*[\$€£₹]?\s*(\d[\d,\.]*)\s*[kK]?",
    re.IGNORECASE,
)
_CURRENCY_SYM = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}


def _parse_salary_string(s: str | None) -> tuple:
    """Very lightweight salary string parser → (min, max, currency, period)."""
    if not s:
        return None, None, None, None
    sym = next((c for c in s if c in _CURRENCY_SYM), None)
    currency = _CURRENCY_SYM.get(sym, "USD")
    m = _SALARY_RE.search(s)
    if not m:
        return None, None, currency, None
    lo = float(m.group(1).replace(",", ""))
    hi = float(m.group(2).replace(",", ""))
    # Handle "k" suffix
    if "k" in s.lower():
        lo *= 1000
        hi *= 1000
    period = "year" if any(w in s.lower() for w in ("year", "annual", "pa", "/yr")) else "year"
    return lo, hi, currency, period


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> None:
    db      = Database()
    fetcher = FreeJobsFetcher(db=db)
    saved   = await fetcher.run(
        source   = args.source,
        search   = args.search,
        category = args.category,
        limit    = args.limit,
    )
    print(f"\n✅  {saved} jobs saved to database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch free remote jobs from Remotive & Himalayas into crwlr DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/free_jobs.py --source all
  python scripts/free_jobs.py --source remotive --category software-dev --limit 200
  python scripts/free_jobs.py --source himalayas --search "machine learning"
  python scripts/free_jobs.py --source all --search "python developer" --limit 100
""",
    )
    parser.add_argument(
        "--source", choices=["remotive", "himalayas", "all"], default="all",
        help="Which API(s) to fetch from (default: all)",
    )
    parser.add_argument("--search",   default=None, help="Keyword search (optional)")
    parser.add_argument("--category", default=None, help="Remotive category slug (e.g. software-dev)")
    parser.add_argument("--limit",    type=int, default=100, help="Max results per source (default: 100)")

    asyncio.run(_main(parser.parse_args()))

