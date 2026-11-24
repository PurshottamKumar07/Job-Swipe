"""
Adzuna Job API Fetcher
======================
Fetches job listings from the Adzuna API and saves them directly to the
SQLite database — using the same `extracted_jobs` table as the scraper,
so the frontend works with zero changes.

Sign up for a free key at: https://developer.adzuna.com/
Then set two environment variables (or add to .env):
    ADZUNA_APP_ID=your_app_id
    ADZUNA_APP_KEY=your_app_key

Usage (CLI):
    python scripts/adzuna.py --query "python developer" --country in --pages 5
    python scripts/adzuna.py --query "machine learning" --where "Bangalore" --country in
    python scripts/adzuna.py --query "software engineer" --country us --salary-min 80000

The fetcher creates a synthetic crawl run so Analytics / Runs pages show Adzuna
fetches alongside regular crawl runs.
"""

import os
import sys
import asyncio
import argparse
import aiohttp
from datetime import datetime, timezone
from urllib.parse import urlencode

# Ensure project root in path for standalone execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

# Country codes supported by Adzuna
SUPPORTED_COUNTRIES = {
    "in": "India",
    "us": "United States",
    "gb": "United Kingdom",
    "ca": "Canada",
    "au": "Australia",
    "de": "Germany",
    "fr": "France",
    "nl": "Netherlands",
    "sg": "Singapore",
    "nz": "New Zealand",
}

DEFAULT_RESULTS_PER_PAGE = 50   # max Adzuna allows
DEFAULT_CONCURRENCY      = 5    # parallel page fetches


# ---------------------------------------------------------------------------
# Adzuna fetcher class
# ---------------------------------------------------------------------------

class AdzunaFetcher:
    """
    Fetches jobs from the Adzuna API and upserts them into the crwlr database.

    Each fetch run is stored as a `crawl_run` with run_type='adzuna' so it
    appears in the UI alongside regular scraper runs.
    """

    def __init__(
        self,
        app_id:    str,
        app_key:   str,
        db:        Database | None = None,
        country:   str = "in",
        concurrency: int = DEFAULT_CONCURRENCY,
    ):
        self.app_id    = app_id
        self.app_key   = app_key
        self.db        = db or Database()
        self.country   = country.lower()
        self.concurrency = concurrency

        self._run_id: int | None = None

        # Stats
        self.fetched   = 0
        self.saved     = 0
        self.errors    = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def fetch(
        self,
        query:       str,
        where:       str | None = None,
        pages:       int = 3,
        salary_min:  int | None = None,
        salary_max:  int | None = None,
        full_time:   bool | None = None,
        max_days_old: int | None = None,
        results_per_page: int = DEFAULT_RESULTS_PER_PAGE,
    ) -> list[dict]:
        """
        Fetch `pages` pages of Adzuna results for `query` and save to DB.
        Returns list of raw job dicts from the API.
        """
        # Create a crawl run only if one wasn't pre-created by the caller (e.g. the API endpoint)
        if self._run_id is None:
            self._run_id = self.db.create_crawl_run(
                run_type="adzuna",
                seed_urls=[f"adzuna:{self.country}:{query}"],
            )
        print(f"[adzuna] Starting fetch — query={query!r}  country={self.country}  pages={pages}  run_id={self._run_id}")

        all_jobs: list[dict] = []
        sem = asyncio.Semaphore(self.concurrency)

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_page(session, sem, query, page_num,
                                 where=where, salary_min=salary_min,
                                 salary_max=salary_max, full_time=full_time,
                                 max_days_old=max_days_old,
                                 results_per_page=results_per_page)
                for page_num in range(1, pages + 1)
            ]
            page_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in page_results:
            if isinstance(result, Exception):
                print(f"[adzuna] Page error: {result}")
                self.errors += 1
            elif result:
                all_jobs.extend(result)

        self.fetched = len(all_jobs)
        print(f"[adzuna] Fetched {self.fetched} listings — saving to DB...")

        # Upsert all into the database
        for job in all_jobs:
            self._save_job(job)

        # Mark the run as finished
        self.db.finish_crawl_run(
            self._run_id,
            status="completed",
            pages_crawled=pages,
            links_inspected=self.fetched,   # re-use links_inspected for total API results
            errors=self.errors,
        )
        print(f"[adzuna] Done — saved {self.saved} jobs  (errors: {self.errors})")
        return all_jobs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_page(
        self,
        session: aiohttp.ClientSession,
        sem:     asyncio.Semaphore,
        query:   str,
        page:    int,
        **kwargs,
    ) -> list[dict]:
        """Fetch a single results page from Adzuna."""
        params: dict = {
            "app_id":           self.app_id,
            "app_key":          self.app_key,
            "results_per_page": kwargs.get("results_per_page", DEFAULT_RESULTS_PER_PAGE),
            "what":             query,
            "content-type":     "application/json",
        }
        if kwargs.get("where"):
            params["where"] = kwargs["where"]
        if kwargs.get("salary_min") is not None:
            params["salary_min"] = kwargs["salary_min"]
        if kwargs.get("salary_max") is not None:
            params["salary_max"] = kwargs["salary_max"]
        if kwargs.get("full_time") is not None:
            params["full_time"] = 1 if kwargs["full_time"] else 0
        if kwargs.get("max_days_old") is not None:
            params["max_days_old"] = kwargs["max_days_old"]

        url = f"{ADZUNA_BASE}/{self.country}/search/{page}?{urlencode(params)}"

        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        print(f"[adzuna] HTTP {resp.status} on page {page}: {body[:200]}")
                        return []
                    data = await resp.json()
                    results = data.get("results", [])
                    print(f"[adzuna] Page {page}: {len(results)} results")
                    return results
            except Exception as exc:
                print(f"[adzuna] Exception fetching page {page}: {exc}")
                self.errors += 1
                return []

    def _save_job(self, job: dict) -> None:
        """Map a raw Adzuna job dict to the extracted_jobs DB schema and upsert."""
        try:
            source_url   = job.get("redirect_url") or job.get("id", "")
            if not source_url:
                return

            title        = job.get("title")
            company      = (job.get("company") or {}).get("display_name")
            location_obj = job.get("location") or {}
            location     = location_obj.get("display_name")

            salary_min_raw  = job.get("salary_min")
            salary_max_raw  = job.get("salary_max")
            salary_min  = float(salary_min_raw)  if salary_min_raw  is not None else None
            salary_max  = float(salary_max_raw)  if salary_max_raw  is not None else None
            # Adzuna salaries are always annual
            salary_currency = "INR" if self.country == "in" else "USD" if self.country == "us" else "GBP"
            salary_period   = "year" if (salary_min or salary_max) else None
            salary_str      = None
            if salary_min and salary_max:
                sym = {"INR": "₹", "USD": "$", "GBP": "£"}.get(salary_currency, "")
                salary_str = f"{sym}{int(salary_min):,} – {sym}{int(salary_max):,} / year"
            elif salary_min:
                sym = {"INR": "₹", "USD": "$", "GBP": "£"}.get(salary_currency, "")
                salary_str = f"{sym}{int(salary_min):,}+ / year"

            description  = job.get("description")  # ~500 chars from Adzuna
            job_type     = _map_job_type(job)
            is_remote    = _is_remote(job)
            posted_at    = job.get("created")       # ISO8601 string from Adzuna

            self.db.insert_extracted_job(
                source_url        = source_url,
                crawl_run_id      = self._run_id,
                source_job_link_id= None,          # no crawl link for API jobs
                title             = title,
                company           = company,
                location          = location,
                salary            = salary_str,
                salary_min        = salary_min,
                salary_max        = salary_max,
                salary_currency   = salary_currency,
                salary_period     = salary_period,
                job_type          = job_type,
                is_remote         = is_remote,
                description       = description,
                apply_url         = source_url,
                posted_at         = posted_at,
                extraction_method = "api",
            )
            self.saved += 1
        except Exception as exc:
            print(f"[adzuna] Save error for {job.get('id')}: {exc}")
            self.errors += 1


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _map_job_type(job: dict) -> str | None:
    """Map Adzuna contract_type / contract_time to our job_type string."""
    ct = (job.get("contract_type") or "").lower()
    cf = (job.get("contract_time") or "").lower()
    if "permanent" in ct or "full" in cf:
        return "full-time"
    if "contract" in ct:
        return "contract"
    if "part" in cf:
        return "part-time"
    return None


def _is_remote(job: dict) -> bool:
    """Detect remote work from location, title, or category."""
    haystack = " ".join(filter(None, [
        (job.get("location") or {}).get("display_name", ""),
        job.get("title", ""),
        job.get("description", ""),
        (job.get("category") or {}).get("label", ""),
    ])).lower()
    return any(kw in haystack for kw in ["remote", "work from home", "wfh", "anywhere"])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _get_credentials() -> tuple[str, str]:
    """Read ADZUNA_APP_ID and ADZUNA_APP_KEY from env or .env file."""
    # Try loading a .env file from the project root
    env_file = os.path.join(_REPO_ROOT, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    app_id  = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    return app_id, app_key


async def _main(args: argparse.Namespace) -> None:
    app_id, app_key = _get_credentials()
    if not app_id or not app_key:
        print(
            "ERROR: Adzuna credentials not found.\n"
            "  Set ADZUNA_APP_ID and ADZUNA_APP_KEY in your environment or in a .env file.\n"
            "  Sign up free at https://developer.adzuna.com/"
        )
        sys.exit(1)

    fetcher = AdzunaFetcher(
        app_id    = app_id,
        app_key   = app_key,
        country   = args.country,
        concurrency = args.concurrency,
    )
    await fetcher.fetch(
        query        = args.query,
        where        = args.where,
        pages        = args.pages,
        salary_min   = args.salary_min,
        salary_max   = args.salary_max,
        full_time    = args.full_time or None,
        max_days_old = args.max_days_old,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch jobs from Adzuna API and save to crwlr DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/adzuna.py --query "python developer" --country in --pages 5
  python scripts/adzuna.py --query "machine learning" --where "Bangalore" --country in
  python scripts/adzuna.py --query "software engineer" --country us --salary-min 80000 --pages 10

Supported countries: in, us, gb, ca, au, de, fr, nl, sg, nz
""",
    )
    parser.add_argument("--query",        required=True,            help="Job search keywords (e.g. 'python developer')")
    parser.add_argument("--country",      default="in",             help="2-letter country code (default: in)")
    parser.add_argument("--where",        default=None,             help="Location filter (e.g. 'Bangalore', 'Mumbai')")
    parser.add_argument("--pages",        type=int, default=3,      help="Number of result pages to fetch (default: 3, 50 jobs/page)")
    parser.add_argument("--salary-min",   type=int, default=None,   dest="salary_min", help="Minimum salary filter")
    parser.add_argument("--salary-max",   type=int, default=None,   dest="salary_max", help="Maximum salary filter")
    parser.add_argument("--full-time",    action="store_true",      dest="full_time",   help="Full-time roles only")
    parser.add_argument("--max-days-old", type=int, default=None,   dest="max_days_old", help="Only jobs posted within N days")
    parser.add_argument("--concurrency",  type=int, default=5,      help="Parallel page fetches (default: 5)")

    asyncio.run(_main(parser.parse_args()))

