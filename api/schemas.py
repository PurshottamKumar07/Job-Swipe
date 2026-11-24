"""
Pydantic schemas for API request / response models.
"""

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class CrawlRequest(BaseModel):
    """Body for POST /api/crawl."""
    seed_urls: list[str] = Field(
        ..., min_length=1,
        description="One or more seed URLs to start crawling from.",
        examples=[["https://stripe.com", "https://github.com/about"]],
    )
    max_pages: int = Field(50, ge=1, le=5000, description="Maximum pages to crawl.")
    concurrency: int = Field(10, ge=1, le=50, description="Max concurrent requests.")
    delay: float = Field(0.25, ge=0, le=10, description="Per-domain delay in seconds.")
    timeout: int = Field(10, ge=1, le=60, description="Request timeout in seconds.")
    respect_robots: bool = Field(False, description="Obey robots.txt rules.")


class ExtractRequest(BaseModel):
    """Body for POST /api/extract."""
    crawl_run_id: int = Field(
        ..., description="ID of the crawl run whose job links to extract.",
    )
    concurrency: int = Field(10, ge=1, le=50, description="Max concurrent requests.")
    timeout: int = Field(10, ge=1, le=60, description="Request timeout in seconds.")


class AdzunaRequest(BaseModel):
    """Body for POST /api/adzuna — trigger an Adzuna API fetch."""
    query: str = Field(..., description="Job search keywords (e.g. 'python developer')")
    country: str = Field("in", description="2-letter Adzuna country code (in/us/gb/ca/au/de/fr/nl/sg/nz)")
    where: str | None = Field(None, description="Location filter (e.g. 'Bangalore')")
    pages: int = Field(3, ge=1, le=20, description="Number of result pages to fetch (50 jobs/page)")
    salary_min: int | None = Field(None, description="Minimum salary filter")
    salary_max: int | None = Field(None, description="Maximum salary filter")
    full_time: bool = Field(False, description="Restrict to full-time roles only")
    max_days_old: int | None = Field(None, description="Only jobs posted within N days")
    concurrency: int = Field(5, ge=1, le=10, description="Parallel page fetches")


class FreeJobsRequest(BaseModel):
    """Body for POST /api/free-jobs — trigger keyless Remotive / Himalayas fetch."""
    source: str = Field("all", description="Source to fetch from: 'remotive', 'himalayas', or 'all'")
    search: str | None = Field(None, description="Keywords to filter jobs by (e.g. 'python', 'react')")
    category: str | None = Field(None, description="Category filter for Remotive (e.g. 'software-dev', 'data')")
    limit: int = Field(50, ge=1, le=500, description="Max jobs to fetch per source")


class JobSpyRequest(BaseModel):
    """Body for POST /api/jobspy — trigger a JobSpy multi-board scrape."""
    search_term: str = Field("software engineer", description="Job search keywords")
    location: str | None = Field(None, description="Location filter (e.g. 'San Francisco, CA')")
    sites: list[str] = Field(
        ["linkedin", "indeed", "glassdoor"],
        description="Sites to scrape: linkedin, indeed, glassdoor, zip_recruiter, google, bayt, naukri, bdjobs, hellowork",
    )
    results_wanted: int = Field(20, ge=1, le=200, description="Number of results per site")
    hours_old: int | None = Field(None, description="Only jobs posted within N hours")
    is_remote: bool = Field(False, description="Filter for remote-only jobs")
    job_type: str | None = Field(
        None, description="Job type: fulltime, parttime, contract, temporary, internship",
    )
    country_indeed: str = Field("usa", description="Country for Indeed/Glassdoor")
    fetch_description: bool = Field(True, description="Fetch full job descriptions (slower but richer)")


class SeedsUpdate(BaseModel):
    """Body for PUT /api/seeds."""
    urls: list[str] = Field(
        ..., min_length=1,
        description="List of seed URLs (replaces existing seeds.txt).",
        examples=[["https://stripe.com", "https://remoteok.com"]],
    )


class ProfilePersonal(BaseModel):
    name: str = "Applicant"
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""


class ProfileSkill(BaseModel):
    name: str
    category: str = "Other"
    level: str = "Intermediate"


class ProfileProject(BaseModel):
    id: str | None = None
    title: str = ""
    link: str = ""
    tags: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class ProfileExperience(BaseModel):
    company: str = ""
    role: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    tags: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)


class ProfileEducation(BaseModel):
    institution: str = ""
    degree: str = ""
    location: str = ""
    graduation_year: str = ""
    gpa: str = ""


class ProfileSettings(BaseModel):
    max_daily_applications: int = 15
    min_delay_seconds: int = 60
    max_delay_seconds: int = 120
    browser_headless: bool = False
    chrome_user_data_dir: str = ""
    chrome_profile_name: str = "Default"


class ProfileUpdateRequest(BaseModel):
    personal: ProfilePersonal = Field(default_factory=ProfilePersonal)
    summary: str = ""
    skills: list[ProfileSkill] = Field(default_factory=list)
    projects: list[ProfileProject] = Field(default_factory=list)
    experience: list[ProfileExperience] = Field(default_factory=list)
    education: list[ProfileEducation] = Field(default_factory=list)
    qa_bank: dict[str, str] = Field(default_factory=dict)
    settings: ProfileSettings = Field(default_factory=ProfileSettings)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class RunResponse(BaseModel):
    id: int
    run_type: str
    seed_urls: str | None = None
    max_pages: int | None = None
    pages_crawled: int
    links_inspected: int
    errors: int
    started_at: str
    finished_at: str | None = None
    status: str
    error_message: str | None = None


class RunCreatedResponse(BaseModel):
    run_id: int
    status: str
    message: str


class JobLinkResponse(BaseModel):
    id: int
    crawl_run_id: int
    url: str
    anchor_text: str | None = None
    found_on: str | None = None
    match_reason: str | None = None
    discovered_at: str


class ExtractedJobResponse(BaseModel):
    id: int
    crawl_run_id: int | None = None
    source_job_link_id: int | None = None
    source_url: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    salary: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    job_type: str | None = None
    is_remote: bool = False
    description: str | None = None
    apply_url: str | None = None
    posted_at: str | None = None
    extraction_method: str | None = None
    extracted_at: str
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    is_active: bool = True
    apply_status: str = "unapplied"
    applied_at: str | None = None
    apply_notes: str | None = None


class AutoApplyStartRequest(BaseModel):
    """Body for POST /api/auto-apply/start."""
    job_ids: list[int] | None = Field(None, description="Specific job IDs to apply to. If omitted, applies to unapplied jobs.")
    max_applications: int = Field(15, ge=1, le=50, description="Max jobs to process in this session.")


class AutoApplyActionRequest(BaseModel):
    """Body for POST /api/auto-apply/action to resume after pause."""
    action: str = Field(..., description="'approve' (with skills), 'skip', or 'solved_captcha'")
    approved_skills: list[str] | None = Field(None, description="List of approved skills to tailor the resume with.")


class AutoApplyMatchResponse(BaseModel):
    job_id: int
    job_title: str
    company: str
    match_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    all_user_skills: list[str]
    recommended_projects: list[dict]
    cover_letter_preview: str


class TailorResumeResponse(BaseModel):
    job_id: int
    job_title: str
    company: str
    match_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    tailored_summary: str
    tailored_experience: list[dict[str, Any]]
    cover_letter: str
    model_used: str


class GenerateResumeResponse(BaseModel):
    job_id: int
    job_title: str
    company: str
    pdf_filename: str
    pdf_url: str
    tex_filename: str
    tex_url: str
    summary_used: str
    cover_letter: str



class AutoApplySessionResponse(BaseModel):
    id: int | None = None
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    total_jobs: int = 0
    applied_jobs: int = 0
    failed_jobs: int = 0
    skipped_jobs: int = 0
    current_job_id: int | None = None
    current_job: dict | None = None
    pause_data: dict | None = None
    daily_applied_today: int = 0
    daily_cap: int = 15


class AutoApplyLogResponse(BaseModel):
    id: int
    session_id: int | None = None
    job_id: int | None = None
    title: str | None = None
    company: str | None = None
    timestamp: str
    event_type: str
    message: str
    metadata: str | None = None


class StatsResponse(BaseModel):
    total_crawl_runs: int
    total_job_links: int
    total_extracted_jobs: int
    active_jobs: int = 0
    remote_jobs: int = 0
    unique_companies: int
    by_method: dict[str, int]
    top_companies: dict[str, int]


class PaginatedJobLinks(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobLinkResponse]


class PaginatedJobs(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ExtractedJobResponse]


class SeedsResponse(BaseModel):
    urls: list[str]
    file_path: str


class JobAlertCreate(BaseModel):
    keyword: str = Field(..., min_length=1, description="Keywords to match (e.g. 'Python', 'React')")
    location: str | None = Field(None, description="Optional location filter")
    frequency: str = Field("Instant", description="'Instant', 'Daily Digest', or 'Weekly Summary'")
    email: str = Field(..., description="Target email for job alerts")


class JobAlertResponse(BaseModel):
    id: int
    keyword: str
    location: str | None = None
    frequency: str
    email: str
    is_active: bool
    created_at: str
    last_sent_at: str | None = None
    match_count: int = 0


class AnalyticsResponse(BaseModel):
    total_jobs: int
    active_jobs: int
    remote_jobs: int
    total_crawl_runs: int
    total_job_links: int
    unique_companies: int
    funnel: dict[str, int]
    daily_applications: list[dict]
    by_method: dict[str, int]
    top_companies: list[dict]
    salary_stats: dict
    top_locations: list[dict]

