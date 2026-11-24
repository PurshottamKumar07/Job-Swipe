"""
JobSpy Integration
==================
Wraps the `python-jobspy` package to scrape jobs from LinkedIn, Indeed,
Glassdoor, ZipRecruiter, Google, Bayt, Naukri, BDJobs & HelloWork
and upserts them into the crwlr SQLite database with full deduplication.

Usage (CLI):
    python scripts/jobspy_fetcher.py --search "software engineer" --location "New York"
    python scripts/jobspy_fetcher.py --search "python developer" --sites linkedin,indeed --results 50
    python scripts/jobspy_fetcher.py --search "data analyst" --remote --hours-old 24
"""

import os
import sys
import re
import asyncio
import argparse
from datetime import datetime, timezone

# Ensure project root on path for standalone execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database

# All site names that JobSpy supports
JOBSPY_SITES = [
    "linkedin", "indeed", "zip_recruiter", "glassdoor",
    "google", "bayt", "naukri", "bdjobs", "hellowork", "seek",
]

DEFAULT_SITES = ["linkedin", "indeed", "glassdoor"]


class JobSpyFetcher:
    """
    Fetches jobs via python-jobspy's scrape_jobs() and upserts into the
    crwlr database.  Each fetch is tracked as a crawl_run with
    run_type='jobspy'.  Deduplication is handled by the existing
    insert_extracted_job() upsert logic (keyed on source_url + title).
    """

    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self._run_id: int | None = None
        self.fetched = 0
        self.saved = 0
        self.skipped = 0
        self.errors = 0

    async def run(
        self,
        search_term: str = "software engineer",
        location: str | None = None,
        sites: list[str] | None = None,
        results_wanted: int = 20,
        hours_old: int | None = None,
        is_remote: bool = False,
        job_type: str | None = None,
        country_indeed: str = "usa",
        proxies: list[str] | None = None,
        fetch_description: bool = True,
    ) -> int:
        """
        Main entry point.  Calls jobspy.scrape_jobs() in a thread
        (it is synchronous / uses requests internally) then upserts
        every row into our DB.

        Returns the number of jobs saved.
        """
        # Pre-create the run (so the API can hand back the ID immediately)
        if self._run_id is None:
            site_list = sites or DEFAULT_SITES
            self._run_id = self.db.create_crawl_run(
                run_type="jobspy",
                seed_urls=[f"jobspy:{','.join(site_list)}:{search_term}"],
                max_pages=results_wanted,
            )

        try:
            # Run the blocking scrape_jobs call in a thread pool
            df = await asyncio.to_thread(
                self._scrape,
                search_term=search_term,
                location=location,
                sites=sites,
                results_wanted=results_wanted,
                hours_old=hours_old,
                is_remote=is_remote,
                job_type=job_type,
                country_indeed=country_indeed,
                proxies=proxies,
                fetch_description=fetch_description,
            )

            if df is None or df.empty:
                print("[jobspy] No jobs returned.")
                self.db.finish_crawl_run(
                    self._run_id,
                    status="completed",
                    pages_crawled=0,
                    links_inspected=0,
                    errors=0,
                )
                return 0

            self.fetched = len(df)
            print(f"[jobspy] Scraped {self.fetched} jobs — saving to DB...")

            for _, row in df.iterrows():
                self._save_row(row)

            self.db.finish_crawl_run(
                self._run_id,
                status="completed",
                pages_crawled=1,
                links_inspected=self.fetched,
                errors=self.errors,
            )
            print(
                f"[jobspy] Done — saved {self.saved}  "
                f"skipped {self.skipped}  errors {self.errors}"
            )
            return self.saved

        except Exception as exc:
            print(f"[jobspy] Fatal error: {exc}")
            self.errors += 1
            self.db.finish_crawl_run(
                self._run_id,
                status="failed",
                errors=self.errors,
                error_message=str(exc),
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scrape(
        search_term: str,
        location: str | None,
        sites: list[str] | None,
        results_wanted: int,
        hours_old: int | None,
        is_remote: bool,
        job_type: str | None,
        country_indeed: str,
        proxies: list[str] | None,
        fetch_description: bool,
    ):
        """Call jobspy synchronously (runs inside asyncio.to_thread)."""
        from jobspy import scrape_jobs, Site, JobType, Country

        valid_sites = {s.value for s in Site}
        if sites:
            target_sites = [s.strip().lower() for s in sites if s.strip().lower() in valid_sites]
        else:
            target_sites = DEFAULT_SITES

        if not target_sites:
            target_sites = DEFAULT_SITES

        # Normalize country_indeed
        country = (country_indeed or "usa").strip().lower()
        valid_countries = {c.value for c in Country}
        if country not in valid_countries:
            country = "usa"

        kwargs: dict = {
            "site_name": target_sites,
            "search_term": search_term,
            "results_wanted": results_wanted,
            "country_indeed": country,
            "description_format": "markdown",
            "verbose": 0,
        }
        if location and location.strip():
            kwargs["location"] = location.strip()
        if hours_old:
            try:
                kwargs["hours_old"] = int(hours_old)
            except (ValueError, TypeError):
                pass
        if is_remote:
            kwargs["is_remote"] = True
        if job_type and job_type.strip():
            clean_jt = job_type.strip().lower().replace("-", "").replace(" ", "").replace("_", "")
            valid_jts = {j.value for j in JobType}
            if clean_jt in valid_jts:
                kwargs["job_type"] = clean_jt
        if proxies:
            kwargs["proxies"] = proxies
        if fetch_description:
            kwargs["fetch_description"] = True

        return scrape_jobs(**kwargs)

    def _save_row(self, row) -> None:
        """Map one pandas row from JobSpy → extracted_jobs schema."""
        try:
            source_url = _str(row.get("job_url"))
            if not source_url:
                self.skipped += 1
                return

            title = _str(row.get("title"))
            company = _str(row.get("company"))
            location = _str(row.get("location"))
            description = _str(row.get("description"))
            if description and len(description) > 4000:
                description = description[:4000]

            # Salary
            salary_min = _safe_float(row.get("min_amount"))
            salary_max = _safe_float(row.get("max_amount"))
            salary_currency = _str(row.get("currency")) or "USD"
            interval = _str(row.get("interval"))  # "yearly", "hourly", …
            salary_period = _map_interval(interval)

            # Build a human-readable salary string
            salary_str = None
            if salary_min or salary_max:
                sym = {"USD": "$", "GBP": "£", "EUR": "€", "INR": "₹"}.get(
                    salary_currency, ""
                )
                lo = f"{sym}{int(salary_min):,}" if salary_min else "?"
                hi = f"{sym}{int(salary_max):,}" if salary_max else "?"
                salary_str = f"{lo} – {hi} / {salary_period or 'year'}"

            # Remote flag
            is_remote_val = bool(row.get("is_remote"))

            # Job type
            jt_raw = _str(row.get("job_type"))
            job_type = _map_job_type(jt_raw) if jt_raw else None

            # Posted date
            posted = row.get("date_posted")
            posted_at = None
            if posted is not None:
                try:
                    import pandas as pd
                    if pd.notna(posted):
                        posted_at = str(posted)
                except Exception:
                    posted_at = str(posted) if posted else None

            # Site the job came from
            site = _str(row.get("site"))

            self.db.insert_extracted_job(
                source_url=source_url,
                crawl_run_id=self._run_id,
                title=title,
                company=company,
                location=location,
                salary=salary_str,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=salary_currency,
                salary_period=salary_period,
                job_type=job_type,
                is_remote=is_remote_val,
                description=description,
                apply_url=source_url,
                posted_at=posted_at,
                extraction_method=f"jobspy:{site}" if site else "jobspy",
            )
            self.saved += 1

        except Exception as exc:
            print(f"[jobspy] Save error: {exc}")
            self.errors += 1


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _str(val) -> str | None:
    """Safely convert a possibly-NaN value to str or None."""
    if val is None:
        return None
    try:
        import pandas as pd
        if pd.isna(val):
            return None
    except Exception:
        pass
    s = str(val).strip()
    return s if s else None


def _safe_float(val) -> float | None:
    try:
        if val is None:
            return None
        import pandas as pd
        if pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _map_interval(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.lower()
    if "year" in r or "annual" in r:
        return "year"
    if "month" in r:
        return "month"
    if "hour" in r:
        return "hour"
    if "week" in r:
        return "week"
    if "day" in r:
        return "day"
    return "year"


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
    if "temporary" in r or "temp" in r:
        return "temporary"
    return raw if raw else None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main(args: argparse.Namespace) -> None:
    db = Database()
    fetcher = JobSpyFetcher(db=db)
    saved = await fetcher.run(
        search_term=args.search,
        location=args.location,
        sites=args.sites.split(",") if args.sites else None,
        results_wanted=args.results,
        hours_old=args.hours_old,
        is_remote=args.remote,
        job_type=args.job_type,
        country_indeed=args.country,
        fetch_description=not args.no_description,
    )
    print(f"\n✅  {saved} jobs saved to database.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape jobs from major boards via JobSpy into crwlr DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/jobspy_fetcher.py --search "python developer" --location "Remote"
  python scripts/jobspy_fetcher.py --search "data scientist" --sites linkedin,indeed --results 50
  python scripts/jobspy_fetcher.py --search "frontend" --remote --hours-old 24
  python scripts/jobspy_fetcher.py --search "nurse" --country usa --location "Chicago"
""",
    )
    parser.add_argument(
        "--search", default="software engineer",
        help="Job search keywords (default: 'software engineer')",
    )
    parser.add_argument("--location", default=None, help="Location filter")
    parser.add_argument(
        "--sites", default=None,
        help=f"Comma-separated sites: {', '.join(JOBSPY_SITES)} (default: linkedin,indeed,glassdoor)",
    )
    parser.add_argument(
        "--results", type=int, default=20,
        help="Number of results per site (default: 20)",
    )
    parser.add_argument("--hours-old", type=int, default=None, help="Only jobs posted within N hours")
    parser.add_argument("--remote", action="store_true", help="Filter for remote jobs only")
    parser.add_argument(
        "--job-type", default=None,
        help="Job type filter: fulltime, parttime, contract, temporary, internship",
    )
    parser.add_argument(
        "--country", default="usa",
        help="Country for Indeed/Glassdoor (default: usa)",
    )
    parser.add_argument(
        "--no-description", action="store_true",
        help="Skip fetching full descriptions (faster)",
    )

    asyncio.run(_main(parser.parse_args()))

