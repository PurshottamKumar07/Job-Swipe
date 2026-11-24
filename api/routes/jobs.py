"""
Job routes
==========
GET  /api/links          — list discovered job links (with pagination)
GET  /api/jobs           — list extracted jobs (filtered by company, method, remote, salary, status)
GET  /api/jobs/{id}      — get single job
GET  /api/jobs/search    — full-text search with FTS5
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from scripts.db import Database
from api.deps import get_db
from api.schemas import (
    JobLinkResponse, ExtractedJobResponse,
    PaginatedJobLinks, PaginatedJobs,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Job links (Stage 1 output)
# ---------------------------------------------------------------------------

@router.get("/links", response_model=PaginatedJobLinks)
async def list_links(
    run_id: int | None = Query(None, description="Filter by crawl run ID."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List discovered job links with pagination."""
    total = db.count_job_links(crawl_run_id=run_id)
    links = db.get_job_links(crawl_run_id=run_id, limit=limit, offset=offset)
    return PaginatedJobLinks(
        total=total,
        limit=limit,
        offset=offset,
        items=[JobLinkResponse(**lnk) for lnk in links],
    )


# ---------------------------------------------------------------------------
# Extracted jobs (Stage 2 output)
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=PaginatedJobs)
async def list_jobs(
    company: str | None = Query(None, description="Filter by company name (partial match)."),
    method: str | None = Query(None, description="Filter by extraction method (api, jsonld, html)."),
    is_remote: bool | None = Query(None, description="Filter by remote work status."),
    min_salary: float | None = Query(None, description="Filter by minimum salary threshold."),
    active_only: bool = Query(True, description="Only return active jobs."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List extracted jobs with optional filters and pagination."""
    total = db.count_extracted_jobs(
        company=company,
        method=method,
        is_remote=is_remote,
        min_salary=min_salary,
        active_only=active_only,
    )
    jobs = db.get_extracted_jobs(
        company=company,
        method=method,
        is_remote=is_remote,
        min_salary=min_salary,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return PaginatedJobs(
        total=total,
        limit=limit,
        offset=offset,
        items=[ExtractedJobResponse(**j) for j in jobs],
    )


@router.get("/jobs/search", response_model=PaginatedJobs)
async def search_jobs(
    q: str = Query(..., min_length=1, description="Search query."),
    is_remote: bool | None = Query(None, description="Filter by remote work status."),
    min_salary: float | None = Query(None, description="Filter by minimum salary threshold."),
    active_only: bool = Query(True, description="Only return active jobs."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """Full-text search across job title, company, location, and description using FTS5."""
    total = db.count_search_jobs(
        q,
        active_only=active_only,
        is_remote=is_remote,
        min_salary=min_salary,
    )
    jobs = db.search_jobs(
        q,
        limit=limit,
        offset=offset,
        active_only=active_only,
        is_remote=is_remote,
        min_salary=min_salary,
    )
    return PaginatedJobs(
        total=total,
        limit=limit,
        offset=offset,
        items=[ExtractedJobResponse(**j) for j in jobs],
    )


@router.get("/jobs/{job_id}", response_model=ExtractedJobResponse)
async def get_job(job_id: int, db: Database = Depends(get_db)):
    """Get a single extracted job by ID."""
    conn = db._get_conn()
    row = conn.execute(
        "SELECT * FROM extracted_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Job #{job_id} not found.")
    return ExtractedJobResponse(**dict(row))
