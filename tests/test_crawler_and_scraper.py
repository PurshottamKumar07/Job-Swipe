"""
Comprehensive unit and integration tests for crawling, web scraping, and API.
"""

import os
import sys
import json
import pytest
import asyncio
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from scripts.extract_jobs import (
    parse_salary,
    detect_is_remote,
    _extract_jsonld,
    _extract_html,
    _detect_ats,
    JobExtractor,
    ExtractedJob,
)
from scripts.crwl import JobCrawler, JobLink
from scripts.db import Database
from fastapi.testclient import TestClient
from api.main import app


# ===========================================================================
# 1. Salary Parsing Tests
# ===========================================================================

class TestParseSalary:
    def test_annual_salary_range_dollar(self):
        min_v, max_v, curr, period = parse_salary("$120,000 - $160,000 per year")
        assert min_v == 120000.0
        assert max_v == 160000.0
        assert curr == "USD"
        assert period == "year"

    def test_k_notation_range(self):
        min_v, max_v, curr, period = parse_salary("$100k to $140k/yr")
        assert min_v == 100000.0
        assert max_v == 140000.0
        assert curr == "USD"
        assert period == "year"

    def test_hourly_wage_range(self):
        min_v, max_v, curr, period = parse_salary("$50 - $75 / hr")
        assert min_v == 50.0
        assert max_v == 75.0
        assert curr == "USD"
        assert period == "hour"

    def test_foreign_currency_gbp(self):
        min_v, max_v, curr, period = parse_salary("£45,000 - £65,000 yearly")
        assert min_v == 45000.0
        assert max_v == 65000.0
        assert curr == "GBP"
        assert period == "year"

    def test_foreign_currency_eur(self):
        min_v, max_v, curr, period = parse_salary("€60,000 - €80,000 per annum")
        assert min_v == 60000.0
        assert max_v == 80000.0
        assert curr == "EUR"
        assert period == "year"

    def test_single_salary(self):
        min_v, max_v, curr, period = parse_salary("$135,000 / year")
        assert min_v == 135000.0
        assert max_v == 135000.0
        assert curr == "USD"
        assert period == "year"

    def test_must_not_match_years_of_experience(self):
        # Critical regression: '3 - 5 years of experience' should NOT be parsed as salary
        min_v, max_v, curr, period = parse_salary("We require 3 - 5 years of experience in Python.")
        assert min_v is None, f"Expected None but got {min_v}"
        assert max_v is None

    def test_must_not_match_dates(self):
        # Critical regression: dates like '2024-05-01' should NOT be parsed as salary
        min_v, max_v, curr, period = parse_salary("Job posted on 2024-05-01 for engineering team.")
        assert min_v is None
        assert max_v is None

    def test_must_not_match_hours_or_weeks(self):
        min_v, max_v, curr, period = parse_salary("Flexible schedule: 20 - 30 hours per week of teamwork.")
        assert min_v is None
        assert max_v is None

    def test_empty_or_none(self):
        assert parse_salary(None) == (None, None, None, None)
        assert parse_salary("") == (None, None, None, None)


# ===========================================================================
# 2. Remote Detection Tests
# ===========================================================================

class TestDetectIsRemote:
    def test_remote_in_location(self):
        assert detect_is_remote("Backend Engineer", "Remote, US", "Job description") is True

    def test_remote_in_title(self):
        assert detect_is_remote("Senior Python Developer (Remote)", "San Francisco, CA", "Description") is True

    def test_wfh_or_telecommute(self):
        assert detect_is_remote("Frontend Dev", "Anywhere", "100% WFH role") is True

    def test_remote_in_url(self):
        assert detect_is_remote("Developer", "New York", "Description", "https://example.com/remote-jobs/123") is True

    def test_onsite_job(self):
        assert detect_is_remote("Store Associate", "Chicago, IL", "Must report in person daily to our retail branch.") is False

    def test_explicit_not_remote(self):
        assert detect_is_remote("Engineer", "New York", "Not remote. In-office only.") is False


# ===========================================================================
# 3. JSON-LD Extraction Tests
# ===========================================================================

class TestExtractJsonLd:
    def test_standard_jobposting(self):
        html = """
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Software Engineer",
            "description": "Build high-scale distributed systems.",
            "datePosted": "2026-10-01",
            "hiringOrganization": {
              "@type": "Organization",
              "name": "Acme Corp"
            },
            "jobLocation": {
              "@type": "Place",
              "address": {
                "@type": "PostalAddress",
                "addressLocality": "San Francisco",
                "addressRegion": "CA"
              }
            },
            "baseSalary": {
              "@type": "MonetaryAmount",
              "currency": "USD",
              "value": {
                "@type": "QuantitativeValue",
                "minValue": 140000,
                "maxValue": 180000,
                "unitText": "YEAR"
              }
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        job = _extract_jsonld(html, "https://acme.com/jobs/1")
        assert job is not None
        assert job.title == "Software Engineer"
        assert job.company == "Acme Corp"
        assert job.location == "San Francisco, CA"
        assert job.extraction_method == "jsonld"
        assert job.salary_min == 140000.0
        assert job.salary_max == 180000.0
        assert job.salary_currency == "USD"
        assert job.salary_period == "year"

    def test_graph_structured_jsonld(self):
        html = """
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@graph": [
              {
                "@type": "WebSite",
                "name": "Tech Corp"
              },
              {
                "@type": "JobPosting",
                "title": "Data Scientist",
                "description": "Analyze large datasets and train ML models.",
                "hiringOrganization": {"name": "Tech Corp"},
                "jobLocationType": "TELECOMMUTE"
              }
            ]
          }
          </script>
        </head>
        <body></body>
        </html>
        """
        job = _extract_jsonld(html, "https://techcorp.com/careers/ds")
        assert job is not None
        assert job.title == "Data Scientist"
        assert job.company == "Tech Corp"
        assert job.is_remote is True


# ===========================================================================
# 4. HTML Extraction Tests
# ===========================================================================

class TestExtractHtml:
    def test_og_meta_tags(self):
        html = """
        <html>
        <head>
          <meta property="og:title" content="Lead Platform Engineer" />
          <meta property="og:site_name" content="Stripe" />
          <meta property="og:description" content="Join Stripe to scale our payment infrastructure. Fully remote role." />
        </head>
        <body>
          <h1>Lead Platform Engineer</h1>
        </body>
        </html>
        """
        job = _extract_html(html, "https://stripe.com/jobs/lead-platform")
        assert job.title == "Lead Platform Engineer"
        assert job.company == "Stripe"
        assert job.is_remote is True

    def test_domain_strip_prefix(self):
        # Regression test: www.workday.com should NOT become orkday.com!
        html = "<html><head><title>Job at Workday</title></head><body></body></html>"
        job = _extract_html(html, "https://www.workday.com/careers/1")
        assert job.company != "orkday.com"
        assert "workday" in job.company.lower()


# ===========================================================================
# 5. Crawler URL Classification & Normalization Tests
# ===========================================================================

class TestCrawlerClassification:
    def setup_method(self):
        self.crawler = JobCrawler(seed_urls=["https://example.com"])

    def test_job_path_detection(self):
        reason = self.crawler._classify_job_link("https://example.com/careers/openings", "Explore")
        assert reason is not None
        assert "path_keyword" in reason

    def test_anchor_text_detection(self):
        reason = self.crawler._classify_job_link("https://example.com/team", "Join our team")
        assert reason is not None
        assert "anchor_text" in reason

    def test_non_job_link_rejected(self):
        reason = self.crawler._classify_job_link("https://example.com/privacy-policy", "Privacy Policy")
        assert reason is None

    def test_auth_link_rejected(self):
        reason = self.crawler._classify_job_link("https://remoteok.com/sign-up", "Sign up now")
        assert reason is None

    def test_linkedin_company_page_not_job(self):
        # Regression: linkedin company profile is NOT a job listing
        reason = self.crawler._classify_job_link("https://www.linkedin.com/company/github", "GitHub on LinkedIn")
        assert reason is None

    def test_linkedin_actual_job_accepted(self):
        reason = self.crawler._classify_job_link("https://www.linkedin.com/jobs/view/123456", "View Job")
        assert reason is not None

    def test_url_normalization(self):
        norm1 = self.crawler._normalize_url("HTTPS://EXAMPLE.COM/Careers/")
        norm2 = self.crawler._normalize_url("https://example.com/Careers")
        assert norm1 == norm2 == "https://example.com/Careers"


# ===========================================================================
# 6. Database Upsert, Search, and Pagination Tests
# ===========================================================================

class TestDatabase:
    def test_database_crud_and_freshness(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            db = Database(db_path=db_path)
            run_id = db.create_crawl_run("crawl", seed_urls=["https://example.com"], max_pages=10)
            assert run_id > 0

            # Insert job link
            link_id = db.insert_job_link(run_id, "https://example.com/job/1", "Software Engineer", "https://example.com")
            assert link_id > 0

            # Insert extracted job
            job_id = db.insert_extracted_job(
                source_url="https://example.com/job/1",
                crawl_run_id=run_id,
                source_job_link_id=link_id,
                title="Software Engineer",
                company="Example Inc",
                salary_min=120000.0,
                salary_max=150000.0,
                salary_currency="USD",
                salary_period="year",
                is_remote=True,
                extraction_method="html",
            )
            assert job_id > 0

            # Search job and verify total count
            results = db.search_jobs("Software Engineer")
            assert len(results) >= 1
            assert results[0]["title"] == "Software Engineer"
            assert results[0]["is_remote"] == 1
            assert results[0]["salary_min"] == 120000.0

            total_count = db.count_search_jobs("Software Engineer")
            assert total_count == 1

            # Upsert upgrade (e.g. upgraded from html to jsonld)
            job_id_2 = db.insert_extracted_job(
                source_url="https://example.com/job/1",
                title="Software Engineer",
                company="Example Inc",
                extraction_method="jsonld",
            )
            assert job_id_2 == job_id
            job = db.get_extracted_jobs()[0]
            assert job["extraction_method"] == "jsonld"

            stats = db.get_stats()
            assert stats["total_crawl_runs"] == 1
            assert stats["total_job_links"] == 1
            assert stats["total_extracted_jobs"] == 1
            assert stats["remote_jobs"] == 1

            db.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


# ===========================================================================
# 7. Async Crawler Mock Crawling Test
# ===========================================================================

@pytest.mark.asyncio
async def test_crawler_mock_crawl():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db = Database(db_path=db_path)
        crawler = JobCrawler(
            seed_urls=["https://testcorp.com/home"],
            max_pages=3,
            concurrency=2,
            delay=0.01,
            db=db,
        )

        # Mock HTML responses
        page_html = {
            "https://testcorp.com/home": """
                <html>
                <body>
                  <a href="/about">About Us</a>
                  <a href="/careers/jobs">Careers</a>
                </body>
                </html>
            """,
            "https://testcorp.com/about": """
                <html>
                <body>
                  <a href="/team">Our Team</a>
                  <a href="/careers/jobs">View Openings</a>
                </body>
                </html>
            """,
            "https://testcorp.com/careers/jobs": """
                <html>
                <body>
                  <h1>Job Openings</h1>
                </body>
                </html>
            """,
            "https://testcorp.com/team": "<html><body>Team</body></html>",
        }

        async def mock_fetch_page(session, url):
            return page_html.get(url, "<html><body></body></html>")

        crawler._fetch_page = mock_fetch_page

        discovered = await crawler.crawl()
        assert len(discovered) >= 1
        assert any("/careers/jobs" in jl.url for jl in discovered)
        assert crawler.pages_crawled <= 3

        # Verify DB records
        runs = db.get_all_crawl_runs()
        assert len(runs) == 1
        assert runs[0]["status"] == "completed"
        assert runs[0]["pages_crawled"] == crawler.pages_crawled

        links = db.get_job_links(runs[0]["id"])
        assert len(links) >= 1

        db.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ===========================================================================
# 8. Async Job Extractor Mock Extraction Test
# ===========================================================================

@pytest.mark.asyncio
async def test_extractor_mock_extract():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    try:
        db = Database(db_path=db_path)
        crawl_run_id = db.create_crawl_run("crawl", ["https://example.com"], 5)
        link_id = db.insert_job_link(crawl_run_id, "https://example.com/careers/job1", "Python Dev", "https://example.com")

        extractor = JobExtractor(concurrency=2, delay=0.01, db=db)

        mock_html = """
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Senior Python Architect",
            "hiringOrganization": {"name": "Example Corp"},
            "jobLocation": {"address": "Remote, USA"},
            "baseSalary": {
              "@type": "MonetaryAmount",
              "currency": "USD",
              "value": {
                "minValue": 160000,
                "maxValue": 200000,
                "unitText": "YEAR"
              }
            }
          }
          </script>
        </head>
        <body></body>
        </html>
        """

        async def mock_fetch_html(url, session):
            return mock_html

        with patch("scripts.extract_jobs._fetch_html", side_effect=mock_fetch_html):
            results = await extractor.extract_from_run(crawl_run_id)

        assert len(results) == 1
        assert results[0].title == "Senior Python Architect"
        assert results[0].company == "Example Corp"
        assert results[0].is_remote is True
        assert results[0].salary_min == 160000.0

        # Check in DB
        jobs = db.get_extracted_jobs()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Python Architect"
        assert jobs[0]["is_remote"] == 1
        assert jobs[0]["source_job_link_id"] == link_id

        db.close()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


# ===========================================================================
# 9. FastAPI REST API Integration Tests
# ===========================================================================

class TestFastAPIIntegration:
    @pytest.fixture(autouse=True)
    def setup_api_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            self.test_db_path = tf.name
        self.db = Database(db_path=self.test_db_path)
        app.state.db = self.db
        self.client = TestClient(app)
        yield
        self.db.close()
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_health_endpoints(self):
        res = self.client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

        res2 = self.client.get("/")
        assert res2.status_code == 200
        assert res2.json()["status"] == "ok"

    def test_seeds_endpoints(self):
        res = self.client.get("/api/seeds")
        assert res.status_code == 200
        assert "urls" in res.json()

    def test_crawl_and_extract_flow(self):
        # 1. Start a crawl
        crawl_payload = {
            "seed_urls": ["https://stripe.com"],
            "max_pages": 5,
            "concurrency": 2,
            "delay": 0.1,
            "timeout": 5,
            "respect_robots": False,
        }
        res = self.client.post("/api/crawl", json=crawl_payload)
        assert res.status_code == 202
        run_data = res.json()
        assert "run_id" in run_data
        run_id = run_data["run_id"]

        # 2. Check run details
        res_run = self.client.get(f"/api/runs/{run_id}")
        assert res_run.status_code == 200
        assert res_run.json()["id"] == run_id

        # 3. Insert mock job link for this run
        link_id = self.db.insert_job_link(run_id, "https://stripe.com/jobs/1", "Engineer", "https://stripe.com")

        # 4. Start extract
        res_extract = self.client.post("/api/extract", json={"crawl_run_id": run_id, "concurrency": 2, "timeout": 5})
        assert res_extract.status_code == 202
        extract_run_id = res_extract.json()["run_id"]
        assert extract_run_id > 0

        # 5. Insert mock extracted job
        self.db.insert_extracted_job(
            source_url="https://stripe.com/jobs/1",
            crawl_run_id=extract_run_id,
            source_job_link_id=link_id,
            title="Senior Backend Engineer",
            company="Stripe",
            location="Remote",
            salary="$170,000 - $210,000",
            salary_min=170000.0,
            salary_max=210000.0,
            salary_currency="USD",
            salary_period="year",
            is_remote=True,
            extraction_method="jsonld",
        )

        # 6. Query jobs
        jobs_res = self.client.get("/api/jobs")
        assert jobs_res.status_code == 200
        assert jobs_res.json()["total"] == 1
        assert jobs_res.json()["items"][0]["title"] == "Senior Backend Engineer"

        # 7. Search jobs with pagination total
        search_res = self.client.get("/api/jobs/search?q=Backend")
        assert search_res.status_code == 200
        assert search_res.json()["total"] == 1
        assert len(search_res.json()["items"]) == 1

        # 8. Stats
        stats_res = self.client.get("/api/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["total_job_links"] == 1
        assert stats["total_extracted_jobs"] == 1
        assert stats["remote_jobs"] == 1

        # 9. Test JobSpy scrape endpoint launch
        with patch("scripts.jobspy_fetcher.JobSpyFetcher.run", new_callable=AsyncMock) as mock_jobspy_run:
            mock_jobspy_run.return_value = 5
            res_jobspy = self.client.post("/api/jobspy", json={
                "search_term": "python developer",
                "sites": ["linkedin", "indeed"],
                "results_wanted": 5,
            })
            assert res_jobspy.status_code == 202
            jobspy_run_id = res_jobspy.json()["run_id"]
            assert jobspy_run_id > 0

            # Verify run record in API
            run_res = self.client.get(f"/api/runs/{jobspy_run_id}")
            assert run_res.status_code == 200
            assert run_res.json()["run_type"] == "jobspy"


class TestDatabaseRunErrorMessage:
    def test_run_error_message_recording(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path=db_path)
            try:
                run_id = db.create_crawl_run("jobspy", ["jobspy:linkedin:dev"], max_pages=10)

                # Finish with failed status and error message
                db.finish_crawl_run(
                    run_id,
                    status="failed",
                    errors=1,
                    error_message="ModuleNotFoundError: No module named 'jobspy'",
                )

                run = db.get_crawl_run(run_id)
                assert run is not None
                assert run["status"] == "failed"
                assert run["errors"] == 1
                assert run["error_message"] == "ModuleNotFoundError: No module named 'jobspy'"

                all_runs = db.get_all_crawl_runs()
                assert len(all_runs) == 1
                assert all_runs[0]["error_message"] == "ModuleNotFoundError: No module named 'jobspy'"
            finally:
                db.close()


class TestJobSpyFetcherNormalization:
    def test_scrape_normalizes_inputs(self):
        from scripts.jobspy_fetcher import JobSpyFetcher
        with patch("jobspy.scrape_jobs") as mock_scrape:
            mock_scrape.return_value = None
            JobSpyFetcher._scrape(
                search_term="python developer",
                location="  Remote  ",
                sites=["LINKEDIN", "invalid_site", "indeed"],
                results_wanted=10,
                hours_old="48",
                is_remote=True,
                job_type="full-time",
                country_indeed="USA",
                proxies=None,
                fetch_description=True,
            )
            assert mock_scrape.called
            call_kwargs = mock_scrape.call_args[1]
            assert set(call_kwargs["site_name"]) == {"linkedin", "indeed"}
            assert call_kwargs["country_indeed"] == "usa"
            assert call_kwargs["location"] == "Remote"
            assert call_kwargs["hours_old"] == 48
            assert call_kwargs["job_type"] == "fulltime"
            assert call_kwargs["is_remote"] is True
            assert call_kwargs["fetch_description"] is True


