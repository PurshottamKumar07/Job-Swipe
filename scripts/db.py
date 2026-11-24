"""
Database Layer
==============
SQLite-backed storage for the entire crwlr pipeline.

Tables
------
- crawl_runs        – metadata for each crawl / extraction invocation
- job_links         – URLs discovered by the crawler (Stage 1)
- extracted_jobs    – structured job data pulled from those URLs (Stage 2)

Features
--------
- WAL mode for concurrent reads/writes
- Foreign key enforcement
- FTS5 virtual table for full-text search across titles, companies, locations & descriptions
- Automatic schema migration for existing databases
- Smart upsert with freshness tracking (`first_seen_at`, `last_seen_at`, `is_active`)
- Parsed salary (`salary_min`, `salary_max`, `salary_currency`, `salary_period`) and `is_remote`
"""

import os
import re
import json
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager
from dataclasses import asdict
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

def canonicalize_url(url: str) -> str:
    """
    Normalize and clean job URLs to prevent duplicates caused by tracking parameters,
    session tokens, or varying board URL structures.
    """
    if not url:
        return ""
    try:
        url = url.strip()
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        scheme = (parsed.scheme or "https").lower()
        netloc = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/")

        # LinkedIn: keep clean path e.g. /jobs/view/123456
        if "linkedin.com" in netloc and "/jobs/view/" in path:
            return f"{scheme}://{netloc}{path}"

        # Indeed: keep jk parameter only
        if "indeed.com" in netloc and "/viewjob" in path:
            q_dict = dict(parse_qsl(parsed.query))
            jk = q_dict.get("jk")
            if jk:
                return f"{scheme}://{netloc}{path}?jk={jk}"

        # General tracking parameter stripping
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "refid", "trackingid", "trk", "tracking_id", "fbclid", "gclid",
            "from", "position", "pagenum", "ref", "spref", "sessionid",
        }
        filtered_q = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if k.lower() not in tracking_params
        ]
        query = urlencode(filtered_q)
        return urlunparse((scheme, netloc, path or "/", "", query, ""))
    except Exception:
        return url.strip()

# Default database lives in the project root
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "crwlr.db",
)

# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

_SCHEMA_TABLES = """
-- Each invocation of crwl.py or extract_jobs.py creates a run
CREATE TABLE IF NOT EXISTS crawl_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type        TEXT    NOT NULL CHECK(run_type IN ('crawl', 'extract', 'adzuna', 'api_fetch', 'jobspy')),
    seed_urls       TEXT,              -- JSON array of seed URLs
    max_pages       INTEGER,
    pages_crawled   INTEGER DEFAULT 0,
    links_inspected INTEGER DEFAULT 0,
    errors          INTEGER DEFAULT 0,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    status          TEXT    NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed')),
    error_message   TEXT
);

-- Links discovered by the crawler (Stage 1)
CREATE TABLE IF NOT EXISTS job_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_run_id    INTEGER NOT NULL REFERENCES crawl_runs(id),
    url             TEXT    NOT NULL,
    anchor_text     TEXT,
    found_on        TEXT,
    match_reason    TEXT,
    discovered_at   TEXT    NOT NULL,
    UNIQUE(crawl_run_id, url)
);

-- Structured job data extracted from URLs (Stage 2)
CREATE TABLE IF NOT EXISTS extracted_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    crawl_run_id        INTEGER REFERENCES crawl_runs(id),
    source_job_link_id  INTEGER REFERENCES job_links(id),
    source_url          TEXT    NOT NULL,
    title               TEXT,
    company             TEXT,
    location            TEXT,
    salary              TEXT,              -- raw salary string
    salary_min          REAL,              -- parsed numeric minimum
    salary_max          REAL,              -- parsed numeric maximum
    salary_currency     TEXT,              -- USD, EUR, GBP, etc.
    salary_period       TEXT,              -- 'year' | 'month' | 'hour'
    job_type            TEXT,              -- full-time, part-time, contract, etc.
    is_remote           INTEGER NOT NULL DEFAULT 0, -- 1 if remote, 0 otherwise
    description         TEXT,
    apply_url           TEXT,
    posted_at           TEXT,
    extraction_method   TEXT,              -- api | jsonld | html | failed
    extracted_at        TEXT    NOT NULL,  -- original extraction timestamp
    first_seen_at       TEXT    NOT NULL,  -- first time discovered
    last_seen_at        TEXT    NOT NULL,  -- most recent confirmed active timestamp
    is_active           INTEGER NOT NULL DEFAULT 1, -- 1 active, 0 expired/inactive
    apply_status        TEXT    NOT NULL DEFAULT 'unapplied', -- unapplied | pending_approval | applied | failed | skipped
    applied_at          TEXT,
    apply_notes         TEXT
);

-- Sessions tracking automated job application runs
CREATE TABLE IF NOT EXISTS auto_apply_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    status          TEXT    NOT NULL DEFAULT 'running', -- running | paused_skill_review | paused_captcha | completed | stopped | failed
    total_jobs      INTEGER DEFAULT 0,
    applied_jobs    INTEGER DEFAULT 0,
    failed_jobs     INTEGER DEFAULT 0,
    skipped_jobs    INTEGER DEFAULT 0,
    current_job_id  INTEGER REFERENCES extracted_jobs(id),
    pause_data      TEXT    -- JSON string for current pause details
);

-- Logs for all auto-apply events
CREATE TABLE IF NOT EXISTS auto_apply_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES auto_apply_sessions(id),
    job_id          INTEGER REFERENCES extracted_jobs(id),
    timestamp       TEXT    NOT NULL,
    event_type      TEXT    NOT NULL, -- info | paused_skill_review | paused_captcha | applied | failed | skipped
    message         TEXT,
    metadata        TEXT    -- JSON string
);

-- Alerts configured by user for keyword matching
CREATE TABLE IF NOT EXISTS job_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword         TEXT    NOT NULL,
    location        TEXT,
    frequency       TEXT    NOT NULL DEFAULT 'Instant', -- Instant | Daily Digest | Weekly Summary
    email           TEXT    NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    last_sent_at    TEXT
);
"""

_SCHEMA_INDEXES = """
-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_job_links_url          ON job_links(url);
CREATE INDEX IF NOT EXISTS idx_job_links_run          ON job_links(crawl_run_id);
CREATE INDEX IF NOT EXISTS idx_extracted_run          ON extracted_jobs(crawl_run_id);
CREATE INDEX IF NOT EXISTS idx_extracted_link         ON extracted_jobs(source_job_link_id);
CREATE INDEX IF NOT EXISTS idx_extracted_company      ON extracted_jobs(company);
CREATE INDEX IF NOT EXISTS idx_extracted_method       ON extracted_jobs(extraction_method);
CREATE INDEX IF NOT EXISTS idx_extracted_apply_status ON extracted_jobs(apply_status);
CREATE INDEX IF NOT EXISTS idx_auto_apply_logs_sess   ON auto_apply_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_extracted_active       ON extracted_jobs(is_active);
CREATE INDEX IF NOT EXISTS idx_extracted_remote       ON extracted_jobs(is_remote);
CREATE INDEX IF NOT EXISTS idx_extracted_salary       ON extracted_jobs(salary_min, salary_max);
CREATE INDEX IF NOT EXISTS idx_job_alerts_active      ON job_alerts(is_active);
"""

_SCHEMA = _SCHEMA_TABLES + _SCHEMA_INDEXES


class Database:
    """SQLite database manager for the crwlr pipeline."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def _transaction(self):
        """Yield a cursor inside a BEGIN / COMMIT block; rollback on error."""
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _ensure_schema(self) -> None:
        """Create tables, run migrations for existing databases, and build indexes."""
        conn = self._get_conn()
        conn.executescript(_SCHEMA_TABLES)
        conn.commit()

        # Migrate existing extracted_jobs table if it's missing new columns
        existing_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(extracted_jobs)").fetchall()
        }

        new_columns = [
            ("salary_min", "REAL"),
            ("salary_max", "REAL"),
            ("salary_currency", "TEXT"),
            ("salary_period", "TEXT"),
            ("is_remote", "INTEGER NOT NULL DEFAULT 0"),
            ("first_seen_at", "TEXT"),
            ("last_seen_at", "TEXT"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("apply_status", "TEXT NOT NULL DEFAULT 'unapplied'"),
            ("applied_at", "TEXT"),
            ("apply_notes", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE extracted_jobs ADD COLUMN {col_name} {col_type}")

        conn.commit()

        # Migrate existing crawl_runs table if it's missing error_message column
        crawl_cols = {
            row["name"] for row in conn.execute("PRAGMA table_info(crawl_runs)").fetchall()
        }
        if "error_message" not in crawl_cols:
            conn.execute("ALTER TABLE crawl_runs ADD COLUMN error_message TEXT")
            conn.commit()

        # Now that all columns exist, safely create indexes
        conn.executescript(_SCHEMA_INDEXES)
        conn.commit()

        # Backfill timestamps/defaults for existing rows if needed
        conn.execute("""
            UPDATE extracted_jobs
            SET first_seen_at = COALESCE(first_seen_at, extracted_at, datetime('now')),
                last_seen_at = COALESCE(last_seen_at, extracted_at, datetime('now')),
                is_active = COALESCE(is_active, 1),
                is_remote = COALESCE(is_remote, 0)
            WHERE first_seen_at IS NULL OR last_seen_at IS NULL OR is_active IS NULL OR is_remote IS NULL
        """)
        conn.commit()

        # Clean up any duplicate records keeping the latest one before creating unique index
        try:
            conn.execute("""
                DELETE FROM extracted_jobs
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM extracted_jobs
                    GROUP BY source_url, COALESCE(title, '')
                )
            """)
            conn.commit()
        except Exception:
            pass

        # Create unique expression index for robust deduplication (handles NULL title)
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS uidx_extracted_url_title
                ON extracted_jobs(source_url, COALESCE(title, ''))
            """)
            conn.commit()
        except Exception:
            pass

        # Setup FTS5 virtual table and automatic sync triggers
        try:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS extracted_jobs_fts USING fts5(
                    title,
                    company,
                    location,
                    description,
                    content='extracted_jobs',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS extracted_jobs_ai AFTER INSERT ON extracted_jobs BEGIN
                    INSERT INTO extracted_jobs_fts(rowid, title, company, location, description)
                    VALUES (new.id, new.title, new.company, new.location, new.description);
                END;

                CREATE TRIGGER IF NOT EXISTS extracted_jobs_ad AFTER DELETE ON extracted_jobs BEGIN
                    INSERT INTO extracted_jobs_fts(extracted_jobs_fts, rowid, title, company, location, description)
                    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
                END;

                CREATE TRIGGER IF NOT EXISTS extracted_jobs_au AFTER UPDATE ON extracted_jobs BEGIN
                    INSERT INTO extracted_jobs_fts(extracted_jobs_fts, rowid, title, company, location, description)
                    VALUES ('delete', old.id, old.title, old.company, old.location, old.description);
                    INSERT INTO extracted_jobs_fts(rowid, title, company, location, description)
                    VALUES (new.id, new.title, new.company, new.location, new.description);
                END;
            """)
            conn.commit()

            # Initial sync of FTS5 table if it is currently empty
            fts_count = conn.execute("SELECT COUNT(*) FROM extracted_jobs_fts").fetchone()[0]
            jobs_count = conn.execute("SELECT COUNT(*) FROM extracted_jobs").fetchone()[0]
            if jobs_count > 0 and fts_count == 0:
                conn.execute("""
                    INSERT INTO extracted_jobs_fts(rowid, title, company, location, description)
                    SELECT id, title, company, location, description FROM extracted_jobs
                """)
                conn.commit()
        except sqlite3.OperationalError:
            # FTS5 might not be enabled in some SQLite builds; fallback will be used
            pass

    def close(self) -> None:
        """Close connection if open."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Crawl runs
    # ------------------------------------------------------------------

    def create_crawl_run(
        self,
        run_type: str,
        seed_urls: list[str] | None = None,
        max_pages: int | None = None,
    ) -> int:
        """Insert a new crawl/extract run and return its id."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO crawl_runs
                   (run_type, seed_urls, max_pages, started_at, status)
                   VALUES (?, ?, ?, ?, 'running')""",
                (run_type, json.dumps(seed_urls) if seed_urls else None, max_pages, now),
            )
            return cur.lastrowid

    def finish_crawl_run(
        self,
        run_id: int,
        *,
        pages_crawled: int | None = None,
        links_inspected: int | None = None,
        errors: int | None = None,
        status: str = "completed",
        error_message: str | None = None,
    ) -> None:
        """Mark a crawl run as finished and record final stats."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cur:
            cur.execute(
                """UPDATE crawl_runs
                   SET pages_crawled = COALESCE(?, pages_crawled),
                       links_inspected = COALESCE(?, links_inspected),
                       errors = COALESCE(?, errors),
                       finished_at = ?,
                       status = ?,
                       error_message = ?
                   WHERE id = ?""",
                (pages_crawled, links_inspected, errors, now, status, error_message, run_id),
            )

    def get_all_crawl_runs(self) -> list[dict]:
        """Return all crawl runs, newest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM crawl_runs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_crawl_run(self, run_id: int) -> dict | None:
        """Return a single crawl run by id."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM crawl_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Job links (Stage 1)
    # ------------------------------------------------------------------

    def insert_job_link(
        self,
        crawl_run_id: int,
        url: str,
        anchor_text: str = "",
        found_on: str = "",
        match_reason: str = "",
        discovered_at: str | None = None,
    ) -> int | None:
        """Insert a job link. Returns the row id, or None if duplicate in this run."""
        if discovered_at is None:
            discovered_at = datetime.now(timezone.utc).isoformat()
        try:
            with self._transaction() as cur:
                cur.execute(
                    """INSERT INTO job_links
                       (crawl_run_id, url, anchor_text, found_on, match_reason, discovered_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (crawl_run_id, url, anchor_text, found_on, match_reason, discovered_at),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate URL within the same run; fetch existing row id
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id FROM job_links WHERE crawl_run_id = ? AND url = ?",
                (crawl_run_id, url),
            ).fetchone()
            return row["id"] if row else None

    def insert_job_link_from_dataclass(self, crawl_run_id: int, job_link) -> int | None:
        """Insert a JobLink dataclass instance."""
        d = asdict(job_link)
        return self.insert_job_link(
            crawl_run_id=crawl_run_id,
            url=d["url"],
            anchor_text=d.get("anchor_text", ""),
            found_on=d.get("found_on", ""),
            match_reason=d.get("match_reason", ""),
            discovered_at=d.get("discovered_at"),
        )

    def get_job_link_id_by_url(self, url: str, crawl_run_id: int | None = None) -> int | None:
        """Lookup a job link ID by URL."""
        conn = self._get_conn()
        if crawl_run_id:
            row = conn.execute(
                "SELECT id FROM job_links WHERE url = ? AND crawl_run_id = ? ORDER BY id DESC LIMIT 1",
                (url, crawl_run_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM job_links WHERE url = ? ORDER BY id DESC LIMIT 1",
                (url,),
            ).fetchone()
        return row["id"] if row else None

    def get_job_links(
        self,
        crawl_run_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Return job links with pagination."""
        conn = self._get_conn()
        if crawl_run_id:
            rows = conn.execute(
                "SELECT * FROM job_links WHERE crawl_run_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (crawl_run_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM job_links ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_job_links(self, crawl_run_id: int | None = None) -> int:
        """Return total count of job links."""
        conn = self._get_conn()
        if crawl_run_id:
            return conn.execute(
                "SELECT COUNT(*) FROM job_links WHERE crawl_run_id = ?",
                (crawl_run_id,),
            ).fetchone()[0]
        return conn.execute("SELECT COUNT(*) FROM job_links").fetchone()[0]

    # ------------------------------------------------------------------
    # Extracted jobs (Stage 2)
    # ------------------------------------------------------------------

    def insert_extracted_job(
        self,
        source_url: str,
        crawl_run_id: int | None = None,
        source_job_link_id: int | None = None,
        title: str | None = None,
        company: str | None = None,
        location: str | None = None,
        salary: str | None = None,
        salary_min: float | None = None,
        salary_max: float | None = None,
        salary_currency: str | None = None,
        salary_period: str | None = None,
        job_type: str | None = None,
        is_remote: bool = False,
        description: str | None = None,
        apply_url: str | None = None,
        posted_at: str | None = None,
        extraction_method: str = "none",
        extracted_at: str | None = None,
    ) -> int | None:
        """
        Insert an extracted job or update an existing one (upsert).
        Updates freshness timestamps and enriches any previously missing fields.
        Returns the job id.
        """
        now = datetime.now(timezone.utc).isoformat()
        if extracted_at is None:
            extracted_at = now

        # Normalize and canonicalize URLs to strip tracking tokens
        source_url = canonicalize_url(source_url)
        if apply_url:
            apply_url = canonicalize_url(apply_url)

        # If source_job_link_id was not provided, attempt to resolve it
        if source_job_link_id is None:
            source_job_link_id = self.get_job_link_id_by_url(source_url, crawl_run_id=crawl_run_id)

        with self._transaction() as cur:
            # 1. First check by canonical source_url + title
            existing = None
            if source_url:
                existing = cur.execute(
                    """SELECT id, title, company, location, salary, salary_min, salary_max,
                              salary_currency, salary_period, job_type, is_remote, description,
                              apply_url, posted_at, extraction_method, source_job_link_id
                       FROM extracted_jobs
                       WHERE source_url = ? AND COALESCE(title, '') = COALESCE(?, '')
                       LIMIT 1""",
                    (source_url, title),
                ).fetchone()

            # 2. Cross-board deduplication: check if same company and title already exists
            if not existing and company and title:
                c_clean = company.strip().lower()
                t_clean = title.strip().lower()
                l_clean = (location or "").strip().lower()
                existing = cur.execute(
                    """SELECT id, title, company, location, salary, salary_min, salary_max,
                              salary_currency, salary_period, job_type, is_remote, description,
                              apply_url, posted_at, extraction_method, source_job_link_id
                       FROM extracted_jobs
                       WHERE LOWER(TRIM(COALESCE(company, ''))) = ?
                         AND LOWER(TRIM(COALESCE(title, ''))) = ?
                         AND (
                             (is_remote = 1 AND ? = 1) OR
                             (? != '' AND LOWER(TRIM(COALESCE(location, ''))) = ?) OR
                             (? = '' OR location IS NULL OR location = '')
                         )
                       ORDER BY id DESC LIMIT 1""",
                    (c_clean, t_clean, 1 if is_remote else 0, l_clean, l_clean, l_clean),
                ).fetchone()

            if existing:
                row_id = existing["id"]
                # Update freshness and enrich null/weaker attributes
                cur.execute(
                    """UPDATE extracted_jobs
                       SET last_seen_at = ?,
                           is_active = 1,
                           crawl_run_id = COALESCE(?, crawl_run_id),
                           source_job_link_id = COALESCE(?, source_job_link_id),
                           title = COALESCE(?, title),
                           company = COALESCE(?, company),
                           location = COALESCE(?, location),
                           salary = COALESCE(?, salary),
                           salary_min = COALESCE(?, salary_min),
                           salary_max = COALESCE(?, salary_max),
                           salary_currency = COALESCE(?, salary_currency),
                           salary_period = COALESCE(?, salary_period),
                           job_type = COALESCE(?, job_type),
                           is_remote = CASE WHEN ? = 1 THEN 1 ELSE is_remote END,
                           description = CASE
                               WHEN LENGTH(COALESCE(?, '')) > LENGTH(COALESCE(description, '')) THEN ?
                               ELSE description
                           END,
                           apply_url = COALESCE(?, apply_url),
                           posted_at = COALESCE(?, posted_at),
                           extraction_method = CASE
                               WHEN extraction_method = 'failed' AND ? != 'failed' THEN ?
                               WHEN extraction_method = 'html' AND ? IN ('api', 'jsonld') THEN ?
                               ELSE extraction_method
                           END
                       WHERE id = ?""",
                    (
                        now,
                        crawl_run_id,
                        source_job_link_id,
                        title,
                        company,
                        location,
                        salary,
                        salary_min,
                        salary_max,
                        salary_currency,
                        salary_period,
                        job_type,
                        1 if is_remote else 0,
                        description, description,
                        apply_url,
                        posted_at,
                        extraction_method, extraction_method,
                        extraction_method, extraction_method,
                        row_id,
                    ),
                )
                return row_id
            else:
                cur.execute(
                    """INSERT INTO extracted_jobs
                       (crawl_run_id, source_job_link_id, source_url,
                        title, company, location, salary,
                        salary_min, salary_max, salary_currency, salary_period,
                        job_type, is_remote, description, apply_url, posted_at,
                        extraction_method, extracted_at, first_seen_at, last_seen_at, is_active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                    (
                        crawl_run_id,
                        source_job_link_id,
                        source_url,
                        title,
                        company,
                        location,
                        salary,
                        salary_min,
                        salary_max,
                        salary_currency,
                        salary_period,
                        job_type,
                        1 if is_remote else 0,
                        description,
                        apply_url,
                        posted_at,
                        extraction_method,
                        extracted_at,
                        extracted_at,
                        now,
                    ),
                )
                return cur.lastrowid

    def insert_extracted_job_from_dataclass(
        self,
        extracted_job,
        crawl_run_id: int | None = None,
        source_job_link_id: int | None = None,
    ) -> int | None:
        """Insert an ExtractedJob dataclass instance."""
        d = asdict(extracted_job)
        return self.insert_extracted_job(
            crawl_run_id=crawl_run_id,
            source_job_link_id=source_job_link_id or d.get("source_job_link_id"),
            source_url=d["source_url"],
            title=d.get("title"),
            company=d.get("company"),
            location=d.get("location"),
            salary=d.get("salary"),
            salary_min=d.get("salary_min"),
            salary_max=d.get("salary_max"),
            salary_currency=d.get("salary_currency"),
            salary_period=d.get("salary_period"),
            job_type=d.get("job_type"),
            is_remote=d.get("is_remote", False),
            description=d.get("description"),
            apply_url=d.get("apply_url"),
            posted_at=d.get("posted_at"),
            extraction_method=d.get("extraction_method", "none"),
            extracted_at=d.get("extracted_at"),
        )

    # ------------------------------------------------------------------
    # Queries & Full-Text Search
    # ------------------------------------------------------------------

    def get_extracted_job_by_id(self, job_id: int) -> dict | None:
        """Return a single extracted job by id."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM extracted_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_extracted_jobs(
        self,
        company: str | None = None,
        method: str | None = None,
        is_remote: bool | None = None,
        min_salary: float | None = None,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Return extracted jobs with optional filters and pagination."""
        conn = self._get_conn()
        clauses: list[str] = []
        params: list = []

        if active_only:
            clauses.append("is_active = 1")
        if company:
            clauses.append("company LIKE ?")
            params.append(f"%{company}%")
        if method:
            clauses.append("extraction_method = ?")
            params.append(method)
        if is_remote is not None:
            clauses.append("is_remote = ?")
            params.append(1 if is_remote else 0)
        if min_salary is not None:
            clauses.append("(salary_max >= ? OR (salary_max IS NULL AND salary_min >= ?))")
            params.extend([min_salary, min_salary])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])

        rows = conn.execute(
            f"SELECT * FROM extracted_jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def count_extracted_jobs(
        self,
        company: str | None = None,
        method: str | None = None,
        is_remote: bool | None = None,
        min_salary: float | None = None,
        active_only: bool = True,
    ) -> int:
        """Count extracted jobs matching the given filters."""
        conn = self._get_conn()
        clauses: list[str] = []
        params: list = []

        if active_only:
            clauses.append("is_active = 1")
        if company:
            clauses.append("company LIKE ?")
            params.append(f"%{company}%")
        if method:
            clauses.append("extraction_method = ?")
            params.append(method)
        if is_remote is not None:
            clauses.append("is_remote = ?")
            params.append(1 if is_remote else 0)
        if min_salary is not None:
            clauses.append("(salary_max >= ? OR (salary_max IS NULL AND salary_min >= ?))")
            params.extend([min_salary, min_salary])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = conn.execute(f"SELECT COUNT(*) FROM extracted_jobs {where}", params).fetchone()
        return row[0] if row else 0

    def search_jobs(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        active_only: bool = True,
        is_remote: bool | None = None,
        min_salary: float | None = None,
    ) -> list[dict]:
        """
        Full-text search across job title, company, location, and description.
        Uses FTS5 virtual table when available with automatic prefix matching,
        falling back to LIKE pattern matching if needed.
        """
        conn = self._get_conn()

        # Try FTS5 first
        try:
            clean_q = re.sub(r"[^\w\s]", " ", query).strip()
            if clean_q:
                # Build prefix query for each token: e.g. "python* engineer*"
                fts_expr = " ".join(f"{word}*" for word in clean_q.split())
                clauses = ["extracted_jobs_fts MATCH ?"]
                params: list = [fts_expr]

                if active_only:
                    clauses.append("j.is_active = 1")
                if is_remote is not None:
                    clauses.append("j.is_remote = ?")
                    params.append(1 if is_remote else 0)
                if min_salary is not None:
                    clauses.append("(j.salary_max >= ? OR (j.salary_max IS NULL AND j.salary_min >= ?))")
                    params.extend([min_salary, min_salary])

                where = f"WHERE {' AND '.join(clauses)}"
                params.extend([limit, offset])

                rows = conn.execute(
                    f"""SELECT j.* FROM extracted_jobs_fts f
                       JOIN extracted_jobs j ON f.rowid = j.id
                       {where}
                       ORDER BY f.rank
                       LIMIT ? OFFSET ?""",
                    params,
                ).fetchall()
                # FTS5 is authoritative — return its results even if empty
                return [dict(r) for r in rows]
        except Exception:
            pass

        # Fallback to standard LIKE matching
        pattern = f"%{query}%"
        clauses = [
            "(title LIKE ? OR company LIKE ? OR location LIKE ? OR description LIKE ?)"
        ]
        params = [pattern, pattern, pattern, pattern]

        if active_only:
            clauses.append("is_active = 1")
        if is_remote is not None:
            clauses.append("is_remote = ?")
            params.append(1 if is_remote else 0)
        if min_salary is not None:
            clauses.append("(salary_max >= ? OR (salary_max IS NULL AND salary_min >= ?))")
            params.extend([min_salary, min_salary])

        where = f"WHERE {' AND '.join(clauses)}"
        params.extend([limit, offset])

        rows = conn.execute(
            f"SELECT * FROM extracted_jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def count_search_jobs(
        self,
        query: str,
        active_only: bool = True,
        is_remote: bool | None = None,
        min_salary: float | None = None,
    ) -> int:
        """Count jobs matching the full-text search query."""
        conn = self._get_conn()
        try:
            clean_q = re.sub(r"[^\w\s]", " ", query).strip()
            if clean_q:
                fts_expr = " ".join(f"{word}*" for word in clean_q.split())
                clauses = ["extracted_jobs_fts MATCH ?"]
                params: list = [fts_expr]

                if active_only:
                    clauses.append("j.is_active = 1")
                if is_remote is not None:
                    clauses.append("j.is_remote = ?")
                    params.append(1 if is_remote else 0)
                if min_salary is not None:
                    clauses.append("(j.salary_max >= ? OR (j.salary_max IS NULL AND j.salary_min >= ?))")
                    params.extend([min_salary, min_salary])

                where = f"WHERE {' AND '.join(clauses)}"
                row = conn.execute(
                    f"""SELECT COUNT(*) FROM extracted_jobs_fts f
                       JOIN extracted_jobs j ON f.rowid = j.id
                       {where}""",
                    params,
                ).fetchone()
                return row[0] if row else 0
        except Exception:
            pass

        pattern = f"%{query}%"
        clauses = [
            "(title LIKE ? OR company LIKE ? OR location LIKE ? OR description LIKE ?)"
        ]
        params = [pattern, pattern, pattern, pattern]

        if active_only:
            clauses.append("is_active = 1")
        if is_remote is not None:
            clauses.append("is_remote = ?")
            params.append(1 if is_remote else 0)
        if min_salary is not None:
            clauses.append("(salary_max >= ? OR (salary_max IS NULL AND salary_min >= ?))")
            params.extend([min_salary, min_salary])

        where = f"WHERE {' AND '.join(clauses)}"
        row = conn.execute(f"SELECT COUNT(*) FROM extracted_jobs {where}", params).fetchone()
        return row[0] if row else 0

    def get_stats(self) -> dict:
        """Return high-level statistics across all data."""
        conn = self._get_conn()
        stats = {}

        stats["total_crawl_runs"] = conn.execute(
            "SELECT COUNT(*) FROM crawl_runs"
        ).fetchone()[0]
        stats["total_job_links"] = conn.execute(
            "SELECT COUNT(*) FROM job_links"
        ).fetchone()[0]
        stats["total_extracted_jobs"] = conn.execute(
            "SELECT COUNT(*) FROM extracted_jobs"
        ).fetchone()[0]
        stats["active_jobs"] = conn.execute(
            "SELECT COUNT(*) FROM extracted_jobs WHERE is_active = 1"
        ).fetchone()[0]
        stats["remote_jobs"] = conn.execute(
            "SELECT COUNT(*) FROM extracted_jobs WHERE is_remote = 1 AND is_active = 1"
        ).fetchone()[0]
        stats["unique_companies"] = conn.execute(
            "SELECT COUNT(DISTINCT company) FROM extracted_jobs WHERE company IS NOT NULL"
        ).fetchone()[0]

        # Jobs by extraction method
        rows = conn.execute(
            "SELECT extraction_method, COUNT(*) as cnt FROM extracted_jobs GROUP BY extraction_method"
        ).fetchall()
        stats["by_method"] = {r["extraction_method"]: r["cnt"] for r in rows}

        # Top companies
        rows = conn.execute(
            """SELECT company, COUNT(*) as cnt FROM extracted_jobs
               WHERE company IS NOT NULL
               GROUP BY company ORDER BY cnt DESC LIMIT 10"""
        ).fetchall()
        stats["top_companies"] = {r["company"]: r["cnt"] for r in rows}

        return stats

    # ------------------------------------------------------------------
    # Auto-Apply Tracking
    # ------------------------------------------------------------------

    def create_auto_apply_session(self, total_jobs: int = 0) -> int:
        """Create a new auto-apply tracking session."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO auto_apply_sessions
                   (started_at, status, total_jobs, applied_jobs, failed_jobs, skipped_jobs)
                   VALUES (?, 'running', ?, 0, 0, 0)""",
                (now, total_jobs),
            )
            return cur.lastrowid

    def update_auto_apply_session(
        self,
        session_id: int,
        *,
        status: str | None = None,
        applied_jobs: int | None = None,
        failed_jobs: int | None = None,
        skipped_jobs: int | None = None,
        current_job_id: int | None = None,
        pause_data: str | None = None,
        is_finished: bool = False,
    ) -> None:
        """Update active session status and counters."""
        now = datetime.now(timezone.utc).isoformat() if is_finished else None
        with self._transaction() as cur:
            cur.execute(
                """UPDATE auto_apply_sessions
                   SET status = COALESCE(?, status),
                       applied_jobs = COALESCE(?, applied_jobs),
                       failed_jobs = COALESCE(?, failed_jobs),
                       skipped_jobs = COALESCE(?, skipped_jobs),
                       current_job_id = COALESCE(?, current_job_id),
                       pause_data = CASE WHEN ? IS NOT NULL THEN ? ELSE pause_data END,
                       finished_at = CASE WHEN ? = 1 THEN ? ELSE finished_at END
                   WHERE id = ?""",
                (
                    status,
                    applied_jobs,
                    failed_jobs,
                    skipped_jobs,
                    current_job_id,
                    pause_data,
                    pause_data,
                    1 if is_finished else 0,
                    now,
                    session_id,
                ),
            )

    def get_auto_apply_session(self, session_id: int) -> dict | None:
        """Fetch session by id."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM auto_apply_sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_latest_auto_apply_session(self) -> dict | None:
        """Fetch newest auto-apply session."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM auto_apply_sessions ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def add_auto_apply_log(
        self,
        session_id: int | None,
        job_id: int | None,
        event_type: str,
        message: str,
        metadata: str | None = None,
    ) -> int:
        """Append a log entry for an auto-apply event."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO auto_apply_logs
                   (session_id, job_id, timestamp, event_type, message, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, job_id, now, event_type, message, metadata),
            )
            return cur.lastrowid

    def get_auto_apply_logs(self, session_id: int | None = None, limit: int = 50) -> list[dict]:
        """Fetch recent auto apply logs."""
        conn = self._get_conn()
        if session_id:
            rows = conn.execute(
                """SELECT l.*, j.title, j.company FROM auto_apply_logs l
                   LEFT JOIN extracted_jobs j ON l.job_id = j.id
                   WHERE l.session_id = ?
                   ORDER BY l.id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT l.*, j.title, j.company FROM auto_apply_logs l
                   LEFT JOIN extracted_jobs j ON l.job_id = j.id
                   ORDER BY l.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_job_apply_status(
        self,
        job_id: int,
        apply_status: str,
        applied_at: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Update job apply status (unapplied, pending_approval, applied, failed, skipped)."""
        now = datetime.now(timezone.utc).isoformat()
        if apply_status == "applied" and not applied_at:
            applied_at = now
        with self._transaction() as cur:
            cur.execute(
                """UPDATE extracted_jobs
                   SET apply_status = ?,
                       applied_at = COALESCE(?, applied_at),
                       apply_notes = COALESCE(?, apply_notes)
                   WHERE id = ?""",
                (apply_status, applied_at, notes, job_id),
            )

    def count_applications_today(self) -> int:
        """Count jobs applied today (UTC date) for daily rate-limiting checks."""
        conn = self._get_conn()
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = conn.execute(
            """SELECT COUNT(*) FROM extracted_jobs
               WHERE apply_status = 'applied' AND applied_at LIKE ?""",
            (f"{today_prefix}%",),
        ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Job Alerts
    # ------------------------------------------------------------------

    def create_job_alert(
        self,
        keyword: str,
        email: str,
        location: str | None = None,
        frequency: str = "Instant",
    ) -> int:
        """Create a new job alert."""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as cur:
            cur.execute(
                """INSERT INTO job_alerts (keyword, location, frequency, email, is_active, created_at)
                   VALUES (?, ?, ?, ?, 1, ?)""",
                (keyword.strip(), location.strip() if location else None, frequency, email.strip(), now),
            )
            return cur.lastrowid

    def get_job_alerts(self) -> list[dict]:
        """Fetch all job alerts with their current match counts."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM job_alerts ORDER BY id DESC").fetchall()
        alerts = []
        for r in rows:
            alert = dict(r)
            alert["match_count"] = self.count_alert_matches(alert["keyword"], alert.get("location"))
            alerts.append(alert)
        return alerts

    def get_job_alert(self, alert_id: int) -> dict | None:
        """Fetch single job alert by ID."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM job_alerts WHERE id = ?", (alert_id,)).fetchone()
        return dict(row) if row else None

    def toggle_job_alert(self, alert_id: int) -> bool:
        """Toggle active status for a job alert."""
        with self._transaction() as cur:
            row = cur.execute("SELECT is_active FROM job_alerts WHERE id = ?", (alert_id,)).fetchone()
            if not row:
                return False
            new_status = 0 if row["is_active"] == 1 else 1
            cur.execute("UPDATE job_alerts SET is_active = ? WHERE id = ?", (new_status, alert_id))
            return True

    def delete_job_alert(self, alert_id: int) -> bool:
        """Delete a job alert."""
        with self._transaction() as cur:
            cur.execute("DELETE FROM job_alerts WHERE id = ?", (alert_id,))
            return cur.rowcount > 0

    def count_alert_matches(self, keyword: str, location: str | None = None) -> int:
        """Count active jobs matching an alert's keyword and optional location."""
        conn = self._get_conn()
        pattern = f"%{keyword.strip()}%"
        if location and location.strip():
            loc_pat = f"%{location.strip()}%"
            row = conn.execute(
                """SELECT COUNT(*) FROM extracted_jobs
                   WHERE is_active = 1
                     AND (title LIKE ? OR description LIKE ? OR company LIKE ?)
                     AND location LIKE ?""",
                (pattern, pattern, pattern, loc_pat),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT COUNT(*) FROM extracted_jobs
                   WHERE is_active = 1
                     AND (title LIKE ? OR description LIKE ? OR company LIKE ?)""",
                (pattern, pattern, pattern),
            ).fetchone()
        return row[0] if row else 0

    def get_alert_matches(self, alert_id: int, limit: int = 20) -> list[dict]:
        """Fetch active jobs matching a given alert ID."""
        alert = self.get_job_alert(alert_id)
        if not alert:
            return []
        conn = self._get_conn()
        pattern = f"%{alert['keyword'].strip()}%"
        loc = alert.get("location")
        if loc and loc.strip():
            loc_pat = f"%{loc.strip()}%"
            rows = conn.execute(
                """SELECT * FROM extracted_jobs
                   WHERE is_active = 1
                     AND (title LIKE ? OR description LIKE ? OR company LIKE ?)
                     AND location LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (pattern, pattern, pattern, loc_pat, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM extracted_jobs
                   WHERE is_active = 1
                     AND (title LIKE ? OR description LIKE ? OR company LIKE ?)
                   ORDER BY id DESC LIMIT ?""",
                (pattern, pattern, pattern, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    def get_analytics_summary(self) -> dict:
        """Return comprehensive analytics for application funnel, crawl trends, and salaries."""
        conn = self._get_conn()
        data = {}

        data["total_jobs"] = conn.execute("SELECT COUNT(*) FROM extracted_jobs").fetchone()[0]
        data["active_jobs"] = conn.execute("SELECT COUNT(*) FROM extracted_jobs WHERE is_active = 1").fetchone()[0]
        data["remote_jobs"] = conn.execute("SELECT COUNT(*) FROM extracted_jobs WHERE is_remote = 1 AND is_active = 1").fetchone()[0]
        data["total_crawl_runs"] = conn.execute("SELECT COUNT(*) FROM crawl_runs").fetchone()[0]
        data["total_job_links"] = conn.execute("SELECT COUNT(*) FROM job_links").fetchone()[0]
        data["unique_companies"] = conn.execute("SELECT COUNT(DISTINCT company) FROM extracted_jobs WHERE company IS NOT NULL AND company != ''").fetchone()[0]

        # Application funnel counts
        rows = conn.execute(
            "SELECT apply_status, COUNT(*) as cnt FROM extracted_jobs GROUP BY apply_status"
        ).fetchall()
        by_status = {r["apply_status"]: r["cnt"] for r in rows}
        data["funnel"] = {
            "unapplied": by_status.get("unapplied", 0),
            "pending_approval": by_status.get("pending_approval", 0),
            "applied": by_status.get("applied", 0),
            "interview": by_status.get("interview", 0),
            "offer": by_status.get("offer", 0),
            "rejected": by_status.get("rejected", 0),
            "skipped": by_status.get("skipped", 0),
            "failed": by_status.get("failed", 0),
        }

        # Daily applications in last 14 days
        daily_rows = conn.execute(
            """SELECT SUBSTR(applied_at, 1, 10) as day, COUNT(*) as cnt
               FROM extracted_jobs
               WHERE applied_at IS NOT NULL AND apply_status IN ('applied', 'interview', 'offer')
               GROUP BY day ORDER BY day DESC LIMIT 14"""
        ).fetchall()
        data["daily_applications"] = [{"date": r["day"], "count": r["cnt"]} for r in reversed(daily_rows)]

        # Extraction methods breakdown
        method_rows = conn.execute(
            "SELECT extraction_method, COUNT(*) as cnt FROM extracted_jobs GROUP BY extraction_method"
        ).fetchall()
        data["by_method"] = {r["extraction_method"] or "unknown": r["cnt"] for r in method_rows}

        # Top 10 hiring companies
        top_comp = conn.execute(
            """SELECT company, COUNT(*) as total_jobs,
                      SUM(CASE WHEN is_remote = 1 THEN 1 ELSE 0 END) as remote_count,
                      SUM(CASE WHEN apply_status = 'applied' THEN 1 ELSE 0 END) as applied_count
               FROM extracted_jobs
               WHERE company IS NOT NULL AND company != ''
               GROUP BY company ORDER BY total_jobs DESC LIMIT 10"""
        ).fetchall()
        data["top_companies"] = [
            {
                "company": r["company"],
                "total_jobs": r["total_jobs"],
                "remote_count": r["remote_count"],
                "applied_count": r["applied_count"],
            }
            for r in top_comp
        ]

        # Salary distribution
        sal_stats = conn.execute(
            """SELECT AVG(salary_min) as avg_min, AVG(salary_max) as avg_max,
                      COUNT(*) as disclosed_count
               FROM extracted_jobs
               WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL"""
        ).fetchone()
        data["salary_stats"] = {
            "avg_min": round(sal_stats["avg_min"], 2) if sal_stats["avg_min"] else None,
            "avg_max": round(sal_stats["avg_max"], 2) if sal_stats["avg_max"] else None,
            "disclosed_count": sal_stats["disclosed_count"] or 0,
        }

        # Top locations
        loc_rows = conn.execute(
            """SELECT location, COUNT(*) as cnt FROM extracted_jobs
               WHERE location IS NOT NULL AND location != ''
               GROUP BY location ORDER BY cnt DESC LIMIT 8"""
        ).fetchall()
        data["top_locations"] = [{"location": r["location"], "count": r["cnt"]} for r in loc_rows]

        return data

