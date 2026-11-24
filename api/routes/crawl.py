"""
Crawl & Extract routes
======================
POST /api/crawl     — launch a crawl in the background
POST /api/extract   — launch extraction in the background
GET  /api/runs      — list all runs
GET  /api/runs/{id} — get run details
"""

import asyncio
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from scripts.db import Database
from scripts.crwl import JobCrawler
from scripts.extract_jobs import JobExtractor
from scripts.adzuna import AdzunaFetcher
from scripts.free_jobs import FreeJobsFetcher
from scripts.jobspy_fetcher import JobSpyFetcher
from api.deps import get_db
from api.schemas import (
    CrawlRequest, ExtractRequest, AdzunaRequest, FreeJobsRequest, JobSpyRequest,
    RunResponse, RunCreatedResponse,
)

router = APIRouter()

# In-memory tracking of background tasks
_active_tasks: dict[int, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------

async def _run_crawl(db: Database, req: CrawlRequest) -> None:
    """Background coroutine that runs a full crawl."""
    crawler = JobCrawler(
        seed_urls=req.seed_urls,
        max_pages=req.max_pages,
        request_timeout=req.timeout,
        delay=req.delay,
        concurrency=req.concurrency,
        respect_robots=req.respect_robots,
        db=db,
    )
    try:
        await crawler.crawl()
        crawler.save_results("job_links.json")
    except Exception as e:
        print(f"[crawl error] {e}")
        if crawler._run_id:
            db.finish_crawl_run(crawler._run_id, status="failed", errors=1, error_message=str(e))


async def _run_extract(db: Database, crawl_run_id: int, extract_run_id: int, req: ExtractRequest) -> None:
    """Background coroutine that runs extraction for a specific crawl run."""
    extractor = JobExtractor(
        timeout=req.timeout,
        concurrency=req.concurrency,
        db=db,
    )

    try:
        results = await extractor.extract_from_run(crawl_run_id, run_id=extract_run_id)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        extractor.save(results, os.path.join(base_dir, "extracted_jobs.json"))
    except Exception as e:
        print(f"[extract error] {e}")
        db.finish_crawl_run(extract_run_id, status="failed", errors=1, error_message=str(e))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/crawl", response_model=RunCreatedResponse, status_code=202)
async def start_crawl(req: CrawlRequest, db: Database = Depends(get_db)):
    """
    Launch a new crawl in the background.

    Returns immediately with the run ID. Poll `GET /api/runs/{id}` for status.
    """
    # Pre-create the run so we can return the ID immediately
    run_id = db.create_crawl_run(
        run_type="crawl",
        seed_urls=req.seed_urls,
        max_pages=req.max_pages,
    )

    async def _background():
        crawler = JobCrawler(
            seed_urls=req.seed_urls,
            max_pages=req.max_pages,
            request_timeout=req.timeout,
            delay=req.delay,
            concurrency=req.concurrency,
            respect_robots=req.respect_robots,
            db=db,
        )
        # Set pre-created run_id so crawl() doesn't create a duplicate
        crawler._run_id = run_id
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            await crawler.crawl()
            crawler.save_results(os.path.join(base_dir, "job_links.json"))
        except Exception as e:
            print(f"[crawl error] {e}")
            db.finish_crawl_run(run_id, status="failed", errors=1, error_message=str(e))

    task = asyncio.create_task(_background())
    _active_tasks[run_id] = task

    return RunCreatedResponse(
        run_id=run_id,
        status="running",
        message=f"Crawl started. Poll GET /api/runs/{run_id} for progress.",
    )


@router.post("/extract", response_model=RunCreatedResponse, status_code=202)
async def start_extract(req: ExtractRequest, db: Database = Depends(get_db)):
    """
    Launch extraction for a completed crawl run.

    Reads job links from the database (not a JSON file) and extracts
    structured job data from each URL in the background.
    """
    # Verify the crawl run exists
    run = db.get_crawl_run(req.crawl_run_id)
    if not run:
        raise HTTPException(404, f"Crawl run #{req.crawl_run_id} not found.")

    links = db.get_job_links(crawl_run_id=req.crawl_run_id, limit=10000)
    if not links:
        raise HTTPException(
            400,
            f"Crawl run #{req.crawl_run_id} has no job links to extract.",
        )

    # Pre-create the extract run so callers can poll it
    extract_run_id = db.create_crawl_run(
        run_type="extract",
        max_pages=len(links),
    )

    task = asyncio.create_task(_run_extract(db, req.crawl_run_id, extract_run_id, req))
    _active_tasks[extract_run_id] = task

    return RunCreatedResponse(
        run_id=extract_run_id,
        status="running",
        message=f"Extraction started for crawl run #{req.crawl_run_id} as run #{extract_run_id}. "
                f"Processing {len(links)} job links.",
    )


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(db: Database = Depends(get_db)):
    """List all crawl and extraction runs, newest first."""
    runs = db.get_all_crawl_runs()
    return [RunResponse(**r) for r in runs]


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: int, db: Database = Depends(get_db)):
    """Get details for a specific run."""
    run = db.get_crawl_run(run_id)
    if not run:
        raise HTTPException(404, f"Run #{run_id} not found.")
    return RunResponse(**run)


@router.post("/adzuna", response_model=RunCreatedResponse, status_code=202)
async def start_adzuna_fetch(req: AdzunaRequest, db: Database = Depends(get_db)):
    """
    Trigger an Adzuna API fetch in the background.

    Requires ADZUNA_APP_ID and ADZUNA_APP_KEY in the server environment or .env file.
    Returns immediately with a run ID; poll GET /api/runs/{id} for status.
    """
    import os

    app_id  = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()

    # Try loading .env from project root
    if not app_id or not app_key:
        env_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            ".env",
        )
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())
            app_id  = os.environ.get("ADZUNA_APP_ID", "").strip()
            app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()

    if not app_id or not app_key:
        from fastapi import HTTPException
        raise HTTPException(
            400,
            "ADZUNA_APP_ID and ADZUNA_APP_KEY are not set. "
            "Add them to a .env file in the project root or set them as environment variables. "
            "Sign up free at https://developer.adzuna.com/",
        )

    # Pre-create the run record so the caller gets an ID immediately
    run_id = db.create_crawl_run(
        run_type="adzuna",
        seed_urls=[f"adzuna:{req.country}:{req.query}"],
        max_pages=req.pages,
    )

    async def _background():
        fetcher = AdzunaFetcher(
            app_id=app_id,
            app_key=app_key,
            db=db,
            country=req.country,
            concurrency=req.concurrency,
        )
        # Reuse the pre-created run ID so AdzunaFetcher doesn't create a duplicate
        fetcher._run_id = run_id
        try:
            await fetcher.fetch(
                query        = req.query,
                where        = req.where,
                pages        = req.pages,
                salary_min   = req.salary_min,
                salary_max   = req.salary_max,
                full_time    = req.full_time or None,
                max_days_old = req.max_days_old,
            )
        except Exception as exc:
            print(f"[adzuna error] {exc}")
            db.finish_crawl_run(run_id, status="failed", errors=1, error_message=str(exc))

    task = asyncio.create_task(_background())
    _active_tasks[run_id] = task

    return RunCreatedResponse(
        run_id=run_id,
        status="running",
        message=(
            f"Adzuna fetch started (query={req.query!r}, country={req.country}, pages={req.pages}). "
            f"Poll GET /api/runs/{run_id} for progress."
        ),
    )


@router.post("/free-jobs", response_model=RunCreatedResponse, status_code=202)
async def start_free_jobs_fetch(req: FreeJobsRequest, db: Database = Depends(get_db)):
    """
    Trigger a free jobs API fetch from Remotive and/or Himalayas (no API keys required).
    Runs asynchronously in the background.
    """
    run_id = db.create_crawl_run(
        run_type="api_fetch",
        seed_urls=[f"{req.source}:{req.search or req.category or 'all'}"],
        max_pages=req.limit,
    )

    async def _background():
        fetcher = FreeJobsFetcher(db=db)
        fetcher._run_id = run_id
        try:
            await fetcher.run(
                source=req.source,
                search=req.search,
                category=req.category,
                limit=req.limit,
            )
        except Exception as exc:
            print(f"[free_jobs error] {exc}")
            db.finish_crawl_run(run_id, status="failed", errors=1, error_message=str(exc))

    task = asyncio.create_task(_background())
    _active_tasks[run_id] = task

    return RunCreatedResponse(
        run_id=run_id,
        status="running",
        message=f"Free jobs fetch started from {req.source}. Check GET /api/runs/{run_id} or browse jobs.",
    )


@router.post("/jobspy", response_model=RunCreatedResponse, status_code=202)
async def start_jobspy_scrape(req: JobSpyRequest, db: Database = Depends(get_db)):
    """
    Trigger a JobSpy multi-board scrape in the background.

    Scrapes from LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google, Bayt,
    Naukri, BDJobs & HelloWork via the python-jobspy package.
    No API key required — uses direct web scraping.
    Deduplication is automatic (keyed on source_url + title).
    """
    run_id = db.create_crawl_run(
        run_type="jobspy",
        seed_urls=[f"jobspy:{','.join(req.sites)}:{req.search_term}"],
        max_pages=req.results_wanted,
    )

    async def _background():
        fetcher = JobSpyFetcher(db=db)
        fetcher._run_id = run_id
        try:
            await fetcher.run(
                search_term=req.search_term,
                location=req.location,
                sites=req.sites,
                results_wanted=req.results_wanted,
                hours_old=req.hours_old,
                is_remote=req.is_remote,
                job_type=req.job_type,
                country_indeed=req.country_indeed,
                fetch_description=req.fetch_description,
            )
        except Exception as exc:
            print(f"[jobspy error] {exc}")
            db.finish_crawl_run(run_id, status="failed", errors=1, error_message=str(exc))

    task = asyncio.create_task(_background())
    _active_tasks[run_id] = task

    return RunCreatedResponse(
        run_id=run_id,
        status="running",
        message=(
            f"JobSpy scrape started (search={req.search_term!r}, "
            f"sites={req.sites}, results={req.results_wanted}). "
            f"Poll GET /api/runs/{run_id} for progress."
        ),
    )


@router.post("/import-existing")
async def import_existing_json(db: Database = Depends(get_db)):
    """Import existing jobs.json and extracted_jobs.json files into SQLite."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    jobs_file = os.path.join(base_dir, "jobs.json")
    if not os.path.exists(jobs_file):
        jobs_file = os.path.join(base_dir, "job_links.json")
    extracted_file = os.path.join(base_dir, "extracted_jobs.json")

    imported_links = 0
    imported_jobs = 0

    crawl_run_id = None
    if os.path.exists(jobs_file):
        try:
            with open(jobs_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("crawl_metadata", {})
            links = data.get("job_links", [])
            crawl_run_id = db.create_crawl_run(
                run_type="crawl",
                seed_urls=meta.get("seed_urls", []),
                max_pages=meta.get("max_pages", 50),
            )
            for lnk in links:
                db.insert_job_link(
                    crawl_run_id=crawl_run_id,
                    url=lnk["url"],
                    anchor_text=lnk.get("anchor_text", ""),
                    found_on=lnk.get("found_on", ""),
                    match_reason=lnk.get("match_reason", ""),
                    discovered_at=lnk.get("discovered_at"),
                )
                imported_links += 1
            db.finish_crawl_run(
                crawl_run_id,
                pages_crawled=meta.get("pages_crawled", len(links)),
                links_inspected=meta.get("links_inspected", len(links)),
                errors=meta.get("errors", 0),
                status="completed",
            )
        except Exception as e:
            print(f"[import jobs.json error] {e}")

    if os.path.exists(extracted_file):
        try:
            from scripts.extract_jobs import parse_salary, detect_is_remote

            with open(extracted_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            jobs = data.get("jobs", [])
            extract_run_id = db.create_crawl_run(
                run_type="extract",
                max_pages=len(jobs),
            )
            for j in jobs:
                link_id = db.get_job_link_id_by_url(j["source_url"])
                s_min = j.get("salary_min")
                s_max = j.get("salary_max")
                s_curr = j.get("salary_currency")
                s_per = j.get("salary_period")
                if s_min is None and (j.get("salary") or j.get("description")):
                    s_min, s_max, s_curr, s_per = parse_salary(j.get("salary") or j.get("description"))

                is_rem = j.get("is_remote")
                if is_rem is None:
                    is_rem = detect_is_remote(j.get("title"), j.get("location"), j.get("description"), j["source_url"])

                db.insert_extracted_job(
                    source_url=j["source_url"],
                    crawl_run_id=extract_run_id,
                    source_job_link_id=link_id,
                    title=j.get("title"),
                    company=j.get("company"),
                    location=j.get("location"),
                    salary=j.get("salary"),
                    salary_min=s_min,
                    salary_max=s_max,
                    salary_currency=s_curr,
                    salary_period=s_per,
                    is_remote=bool(is_rem),
                    job_type=j.get("job_type"),
                    description=j.get("description"),
                    apply_url=j.get("apply_url"),
                    posted_at=j.get("posted_at"),
                    extraction_method=j.get("extraction_method", "html"),
                    extracted_at=j.get("extracted_at"),
                )
                imported_jobs += 1
            db.finish_crawl_run(
                extract_run_id,
                pages_crawled=imported_jobs,
                links_inspected=imported_jobs,
                status="completed",
            )
        except Exception as e:
            print(f"[import extracted_jobs.json error] {e}")

    return {
        "success": True,
        "imported_links": imported_links,
        "imported_jobs": imported_jobs,
        "message": f"Successfully imported {imported_links} links and {imported_jobs} jobs into SQLite.",
    }
