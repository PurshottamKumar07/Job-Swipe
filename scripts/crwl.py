"""
Job Link Crawler (Async)
========================
Crawls through web pages starting from one or more seed URLs (or a file of URLs),
following links across domains, and identifies URLs that look like job postings
or career pages. Uses asyncio + aiohttp for concurrent fetching.

Usage:
    python scripts/crwl.py [<url> ...] [--seeds FILE] [--max-pages N] [--output FILE]

Examples:
    python scripts/crwl.py https://example.com
    python scripts/crwl.py https://example1.com https://example2.com
    python scripts/crwl.py --seeds seeds.txt --max-pages 100 --output jobs.json
    python scripts/crwl.py --seeds seeds.txt --concurrency 20
"""

import os
import re
import sys
import json
import asyncio
import argparse
import aiohttp
from urllib.robotparser import RobotFileParser
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse
from collections import deque
from dataclasses import dataclass, field, asdict

# Ensure project root is in sys.path for standalone script execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database


# ---------------------------------------------------------------------------
# Job-detection patterns
# ---------------------------------------------------------------------------

# URL path segments that strongly indicate an INDIVIDUAL job posting or career listing page.
# More specific than before — avoids broad category pages and marketing pages.
JOB_PATH_KEYWORDS = [
    "/jobs/",          # /jobs/<slug> — a specific job, not just the jobs listing
    "/job/",           # /job/<slug>
    "/careers/",       # /careers/<slug> — specific career page
    "/career/",
    "/opening/",
    "/openings/",
    "/position/",
    "/positions/",
    "/vacancy/",
    "/vacancies/",
    "/apply/",
    "/apply?",
    "/work-with-us",
    "/join-us",
    "/join-our-team",
    "/recruitment",
    "/hiring",
]

# Root-level career listing pages (without a trailing slug) are OK to include
# only if they are the company's own careers page.
# e.g. stripe.com/careers — good.  remoteok.com/remote-marketing-jobs — bad.
JOB_PATH_EXACT = [
    "/careers",
    "/jobs",
    "/openings",
    "/positions",
    "/vacancies",
    "/talent",
    "/work-with-us",
    "/join-us",
]

# URL path segments that mean the page is definitely NOT a job listing for seekers.
NON_JOB_PATH_KEYWORDS = [
    "/sign-up", "/signup", "/signin", "/sign-in", "/login", "/log-in",
    "/auth", "/register", "/privacy", "/terms", "/legal", "/cookie",
    "/pricing", "/billing", "/checkout", "/cart", "/subscribe",
    "/settings", "/account", "/forgot-password", "/reset-password",
    # employer/recruiter-side pages
    "/hire-remotely", "/hire", "/post-a-job", "/post_a_job",
    "/buy-bundle", "/buy_bundle",
    "/premium", "/upgrade",
    # stats and blog pages
    "/remote-work-statistics", "/statistics", "/stats",
    "/blog", "/developer-skills", "/news", "/press",
    # community / discussion / support pages
    "/community/discussions", "/orgs/community", "/discussions",
    "/support", "/help", "/faq",
    # misc marketing
    "/startups", "/enterprise", "/about",
]

# URL query parameters that indicate employer-side posting flows
NON_JOB_QUERY_PARAMS = [
    "ref=top", "ref=nav", "ref=bottombar", "ref=center",
    "discount_code",
]

# Known ATS / job-board domains — if a link points to these, it is very likely a real job
JOB_BOARD_DOMAINS = [
    "lever.co", "greenhouse.io", "workday.com",
    "ashbyhq.com", "myworkdayjobs.com",
    "icims.com", "bamboohr.com", "breezy.hr",
    "recruitee.com", "smartrecruiters.com",
    "jobvite.com", "applytojob.com",
    "jobs.lever.co", "boards.greenhouse.io",
    "wellfound.com",    # AngelList
    "ziprecruiter.com",
]

# Social media / media domains to skip crawling BFS into
SKIP_DOMAINS = frozenset([
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "pinterest.com", "reddit.com",
    "remoteok.com",        # category listing site — not individual postings
    "producthunt.com",     # product discovery, not job listings
])

# Anchor text must match one of these tight patterns to count as a job link
# "career growth", "schedule & cron jobs", "post a job" etc. must NOT match.
JOB_TEXT_PATTERN = re.compile(
    r"\b("
    r"open(?:ing|ings|s)?"            # openings, open positions
    r"|vacanc(?:y|ies)"               # vacancy, vacancies
    r"|we(?:'| a)re hiring"           # we're hiring, we are hiring
    r"|now hiring"
    r"|join (?:us|our team)"
    r"|apply now"
    r"|see (?:all )?(?:open )?(?:job|position|role)s?"
    r"|view (?:all )?(?:open )?(?:job|position|role)s?"
    r"|(?:all )?(?:current )?(?:job|position|role) opening"
    r")",
    re.IGNORECASE,
)

# Compile separately — a URL that contains these is immediately disqualified
# even if the anchor text pattern matches
_NON_JOB_ANCHOR_PATTERN = re.compile(
    r"\b(cron jobs?|batch jobs?|schedule.*job|post a job|hire .* remotely|remote jobs? api)\b",
    re.IGNORECASE,
)

# File extensions to skip entirely
SKIP_EXTENSIONS = frozenset([
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".mp4", ".mp3", ".zip", ".tar", ".gz", ".exe", ".dmg",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".ico",
])


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class JobLink:
    """A single discovered job-related link."""
    url: str
    anchor_text: str
    found_on: str          # the page where the link was discovered
    match_reason: str      # why we flagged it (path_keyword | job_board | anchor_text)
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Async Crawler
# ---------------------------------------------------------------------------

class JobCrawler:
    """
    Async BFS web crawler that follows links across domains and identifies
    URLs related to job postings / career pages.

    Uses aiohttp with true concurrent workers and per-domain delays
    for polite crawling.
    """

    def __init__(
        self,
        seed_urls: list[str] | str,
        max_pages: int = 50,
        request_timeout: int = 10,
        delay: float = 0.25,
        concurrency: int = 10,
        respect_robots: bool = False,
        db: Database | None = None,
    ):
        if isinstance(seed_urls, str):
            self.seed_urls = [seed_urls]
        else:
            self.seed_urls = list(seed_urls)

        self.start_url = self.seed_urls[0] if self.seed_urls else ""
        self.max_pages = max_pages
        self.request_timeout = aiohttp.ClientTimeout(total=request_timeout)
        self.delay = delay
        self.concurrency = concurrency
        self.respect_robots = respect_robots

        # Database
        self.db = db or Database()
        self._run_id: int | None = None

        # Per-domain robots.txt cache: netloc -> RobotFileParser (or None)
        self._robots_cache: dict[str, RobotFileParser | None] = {}

        # Per-domain rate-limit state
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._domain_last_request: dict[str, float] = {}

        # BFS state (thread-safe via asyncio.Queue)
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.visited: set[str] = set()
        self._enqueued: set[str] = set()

        # Worker synchronization
        self._active_workers = 0
        self._stop_event = asyncio.Event()

        # Results
        self.job_links: list[JobLink] = []
        self._seen_job_urls: set[str] = set()

        # Stats
        self.pages_crawled = 0
        self.links_inspected = 0
        self.errors = 0

        # Synchronization
        self._semaphore: asyncio.Semaphore | None = None
        self._lock = asyncio.Lock()  # protects shared state mutations

    # ------------------------------------------------------------------
    # Robots.txt helpers (sync — called once per domain)
    # ------------------------------------------------------------------

    def _get_robots(self, url: str) -> RobotFileParser | None:
        if not self.respect_robots:
            return None
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc in self._robots_cache:
            return self._robots_cache[netloc]

        robots_url = f"{parsed.scheme}://{netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
            self._robots_cache[netloc] = rp
            print(f"  [robots] Loaded robots.txt for {netloc}")
        except Exception:
            self._robots_cache[netloc] = None
            print(f"  [robots] Could not fetch robots.txt for {netloc} — treating as allow-all")
        return self._robots_cache[netloc]

    def _is_allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self._get_robots(url)
        if rp is None:
            return True
        return rp.can_fetch("JobCrawler/1.0", url)

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url.strip())
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.params, parsed.query, ""))

    @staticmethod
    def _should_skip(url: str) -> bool:
        parsed = urlparse(url)
        return any(parsed.path.lower().endswith(ext) for ext in SKIP_EXTENSIONS)

    @staticmethod
    def _is_skip_domain(url: str) -> bool:
        netloc = urlparse(url).netloc.lower().removeprefix("www.")
        return any(netloc == d or netloc.endswith("." + d) for d in SKIP_DOMAINS)

    # ------------------------------------------------------------------
    # Job-detection logic
    # ------------------------------------------------------------------

    def _classify_job_link(self, url: str, anchor_text: str) -> str | None:
        """
        Return a reason string if `url` looks like a genuine job listing or
        company careers page; return None otherwise.

        Rules (applied in order):
        1. Hard-reject non-job path keywords (login, pricing, employer-side, etc.)
        2. Hard-reject query params that indicate employer-side posting flows
        3. Hard-reject anchor text that looks like employer/non-job content
        4. Accept known ATS / job-board domains (Greenhouse, Lever, Ashby, etc.)
        5. Accept paths that contain a job-slug segment (e.g. /jobs/<slug>)
        6. Accept exact company career root pages (e.g. stripe.com/careers)
        7. Accept tight anchor-text patterns (we're hiring, now hiring, openings, etc.)
        """
        lower_url = url.lower()
        parsed = urlparse(lower_url)
        path = parsed.path
        query = parsed.query
        domain = parsed.netloc.removeprefix("www.")

        # ── 0. Special-case: domain itself is a careers TLD (e.g. github.careers) ─
        if domain.endswith(".careers") or domain == "careers":
            return "careers_page:careers_domain"

        # ── 1. Hard-reject bad path keywords ────────────────────────────────
        # Exception: /about/careers and similar paths that END with a valid
        # career path are allowed even if they contain /about.
        # We check the rejected keyword is not shadowed by a valid career suffix.
        path_no_trail_early = path.rstrip("/")
        for bad in NON_JOB_PATH_KEYWORDS:
            if bad in path:
                # Allow if path ends with a valid job segment after the bad one
                # e.g. /about/careers — bad="/about" but ends with "/careers"
                valid_suffix = any(
                    path_no_trail_early == ex or path_no_trail_early.endswith(ex)
                    for ex in JOB_PATH_EXACT
                )
                if not valid_suffix:
                    return None
                break  # has bad keyword but overridden by valid career suffix — continue

        # ── 2. Hard-reject employer-side query params ────────────────────────
        if any(p in query for p in NON_JOB_QUERY_PARAMS):
            return None

        # ── 3. Hard-reject bad anchor text (e.g. "Cron Jobs", "Post a Job") ─
        clean_anchor = anchor_text.strip()
        if _NON_JOB_ANCHOR_PATTERN.search(clean_anchor):
            return None

        # ── 4. Accept known ATS / job-board domains ──────────────────────────
        for jb in JOB_BOARD_DOMAINS:
            if domain == jb or domain.endswith("." + jb):
                # Must have a non-root path so we don't grab the ATS homepage
                if path and path not in ("", "/"):
                    return f"job_board:{jb}"
                return None

        # ── 5. Accept paths with a job-slug (keyword + non-trivial suffix) ───
        for kw in JOB_PATH_KEYWORDS:
            if kw in path:
                # The keyword must be followed by more path, a query, or at end
                # e.g. /jobs/software-engineer  ✓
                # e.g. /jobs                    — handled by exact list below
                idx = path.find(kw)
                suffix = path[idx + len(kw):]
                # Accept if there is a slug after the keyword
                if suffix and suffix not in ("/", ""):
                    return f"path_keyword:{kw.strip('/')}"
                # Accept /careers as a root page (handled next), but not
                # e.g. /remote-marketing-jobs (not in our keyword list)
                # so fall through to exact check

        # ── 6. Accept exact company career root pages ────────────────────────
        # e.g. stripe.com/careers  or  github.com/about/careers
        # but NOT remoteok.com/remote-marketing-jobs
        path_no_trail = path.rstrip("/")
        for exact in JOB_PATH_EXACT:
            if path_no_trail == exact or path_no_trail.endswith(exact):
                # Reject if it's on a known job-aggregator domain — those
                # listing pages are category pages, not company careers pages
                if any(agg in domain for agg in ("remoteok", "producthunt", "reddit",
                                                  "linkedin", "indeed", "glassdoor")):
                    return None
                return f"careers_page:{exact.strip('/')}"

        # ── 7. Tight anchor-text match (last resort, requires clean text) ────
        if 3 < len(clean_anchor) <= 120 and JOB_TEXT_PATTERN.search(clean_anchor):
            # Extra guard: reject if the URL itself looks like a blog/article/stats page
            bad_path_fragments = [
                "/blog", "/news", "/press", "/article", "/post/",
                "/wiki", "/docs", "/guide", "/tutorial",
                "/statistics", "/stats", "#",
                "/discussions", "/community",
            ]
            if any(frag in path for frag in bad_path_fragments):
                return None
            return f"anchor_text:{clean_anchor[:60]}"

        return None

    # ------------------------------------------------------------------
    # Per-domain rate limiting
    # ------------------------------------------------------------------

    async def _domain_delay(self, url: str) -> None:
        """Ensure at least `self.delay` seconds between requests to the same domain."""
        netloc = urlparse(url).netloc.lower()
        async with self._lock:
            if netloc not in self._domain_locks:
                self._domain_locks[netloc] = asyncio.Lock()
            lock = self._domain_locks[netloc]

        async with lock:
            last = self._domain_last_request.get(netloc, 0)
            elapsed = asyncio.get_event_loop().time() - last
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
            self._domain_last_request[netloc] = asyncio.get_event_loop().time()

    # ------------------------------------------------------------------
    # Async fetch
    # ------------------------------------------------------------------

    async def _fetch_page(
        self, session: aiohttp.ClientSession, url: str
    ) -> str | None:
        """Fetch a page, returning the HTML text or None on failure."""
        try:
            await self._domain_delay(url)
            async with session.get(url, allow_redirects=True) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if resp.status != 200 or ("text/html" not in content_type and "application/xhtml+xml" not in content_type):
                    return None
                return await resp.text(errors="replace")
        except Exception:
            async with self._lock:
                self.errors += 1
            return None

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    async def _worker(self, session: aiohttp.ClientSession) -> None:
        """Process URLs from the queue until max_pages is reached or crawl completes."""
        while True:
            async with self._lock:
                if self.pages_crawled >= self.max_pages or self._stop_event.is_set():
                    return

            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                async with self._lock:
                    if self._active_workers == 0 and self.queue.empty():
                        self._stop_event.set()
                        return
                    if self.pages_crawled >= self.max_pages or self._stop_event.is_set():
                        return
                continue

            normalized = self._normalize_url(url)

            async with self._lock:
                if normalized in self.visited or self._should_skip(url):
                    self.queue.task_done()
                    continue
                if self.pages_crawled >= self.max_pages:
                    self.queue.task_done()
                    self._stop_event.set()
                    return

                self.visited.add(normalized)
                self.pages_crawled += 1
                page_num = self.pages_crawled
                self._active_workers += 1

            try:
                print(f"[{page_num:>4}/{self.max_pages}]  Crawling: {url}")

                if not self._is_allowed(url):
                    print(f"         [!] Blocked by robots.txt: {url}")
                    continue

                async with self._semaphore:
                    html = await self._fetch_page(session, url)

                if html is None:
                    continue

                soup = BeautifulSoup(html, "html.parser")

                for anchor in soup.find_all("a", href=True):
                    raw_href = anchor["href"].strip()
                    if not raw_href or raw_href.startswith(("mailto:", "tel:", "javascript:", "#", "sms:")):
                        continue

                    absolute_url = urljoin(url, raw_href)

                    async with self._lock:
                        self.links_inspected += 1

                    anchor_text = anchor.get_text(separator=" ", strip=True)
                    reason = self._classify_job_link(absolute_url, anchor_text)

                    if reason:
                        async with self._lock:
                            if absolute_url not in self._seen_job_urls:
                                self._seen_job_urls.add(absolute_url)
                                job = JobLink(
                                    url=absolute_url,
                                    anchor_text=anchor_text[:200],
                                    found_on=url,
                                    match_reason=reason,
                                )
                                self.job_links.append(job)
                                self.db.insert_job_link_from_dataclass(self._run_id, job)

                                print(f"         [+] JOB LINK  [{reason}]")
                                print(f"           {absolute_url}")
                                print(f'           Text: "{anchor_text[:80]}"')

                    # Enqueue for further crawling
                    norm_link = self._normalize_url(absolute_url)
                    async with self._lock:
                        if (
                            norm_link not in self._enqueued
                            and norm_link not in self.visited
                            and not self._should_skip(absolute_url)
                            and not self._is_skip_domain(absolute_url)
                            and self._is_allowed(absolute_url)
                        ):
                            self._enqueued.add(norm_link)
                            await self.queue.put(absolute_url)
            finally:
                async with self._lock:
                    self._active_workers -= 1
                self.queue.task_done()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def crawl(self) -> list[JobLink]:
        """Run the async BFS crawl. Returns the list of discovered JobLink objects."""
        if self._run_id is None:
            self._run_id = self.db.create_crawl_run(
                run_type="crawl",
                seed_urls=self.seed_urls,
                max_pages=self.max_pages,
            )
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._stop_event.clear()
        self._active_workers = 0

        print(f"\n{'=' * 60}")
        print(f"  Job Crawler starting  (run #{self._run_id})")
        print(f"  Seed URLs ({len(self.seed_urls)}) :")
        for s in self.seed_urls[:5]:
            print(f"    - {s}")
        if len(self.seed_urls) > 5:
            print(f"    ... and {len(self.seed_urls) - 5} more")
        print(f"  Max pages   : {self.max_pages}")
        print(f"  Concurrency : {self.concurrency}")
        print(f"  Database    : {self.db.db_path}")
        print(f"{'=' * 60}\n")

        # Seed the queue
        for url in self.seed_urls:
            norm = self._normalize_url(url)
            self._enqueued.add(norm)
            await self.queue.put(url)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; JobCrawler/1.0; "
                "+https://github.com/example/jobcrawler)"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with aiohttp.ClientSession(
            timeout=self.request_timeout,
            headers=headers,
        ) as session:
            num_workers = min(self.concurrency, self.max_pages)
            workers = [
                asyncio.create_task(self._worker(session))
                for _ in range(num_workers)
            ]
            await asyncio.gather(*workers)

        # Finalize
        self.db.finish_crawl_run(
            self._run_id,
            pages_crawled=self.pages_crawled,
            links_inspected=self.links_inspected,
            errors=self.errors,
            status="completed",
        )
        self._print_summary()
        return self.job_links

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_summary(self) -> None:
        print(f"\n{'=' * 60}")
        print(f"  Crawl complete")
        print(f"{'=' * 60}")
        print(f"  Pages crawled    : {self.pages_crawled}")
        print(f"  Links inspected  : {self.links_inspected}")
        print(f"  Errors           : {self.errors}")
        print(f"  Job links found  : {len(self.job_links)}")
        print(f"{'=' * 60}")

        if self.job_links:
            print(f"\n  Discovered Job Links:")
            print(f"  {'-' * 56}")
            for i, jl in enumerate(self.job_links, 1):
                print(f"  {i:>3}. {jl.url}")
                print(f'       Text   : "{jl.anchor_text[:80]}"')
                print(f"       Found  : {jl.found_on}")
                print(f"       Reason : {jl.match_reason}")
                print()

    def save_results(self, filepath: str) -> None:
        """Save discovered job links to a JSON file."""
        output = {
            "crawl_metadata": {
                "seed_urls": self.seed_urls,
                "max_pages": self.max_pages,
                "pages_crawled": self.pages_crawled,
                "links_inspected": self.links_inspected,
                "errors": self.errors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            "job_links": [asdict(jl) for jl in self.job_links],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\n  Results saved to: {filepath}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Crawl web pages and discover job-related links (async).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="One or more seed URLs to start crawling from.",
    )
    parser.add_argument(
        "--seeds", "-s",
        type=str,
        default=None,
        help="Path to a text file containing seed URLs (one per line).",
    )
    parser.add_argument(
        "--max-pages", "-m",
        type=int,
        default=50,
        help="Maximum number of pages to crawl (default: 50).",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="job_links.json",
        help="Output JSON file path (default: job_links.json).",
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=0.25,
        help="Per-domain delay between requests in seconds (default: 0.25).",
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
    parser.add_argument(
        "--respect-robots", "-r",
        action="store_true",
        default=False,
        help="Obey each site's robots.txt rules (default: off).",
    )

    args = parser.parse_args()

    seed_urls = list(args.urls)

    if args.seeds:
        try:
            with open(args.seeds, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        seed_urls.append(line)
        except OSError as e:
            parser.error(f"Could not read seeds file '{args.seeds}': {e}")

    if not seed_urls:
        parser.error(
            "No seed URLs provided. Provide at least one URL argument or use --seeds <file>.\n"
            "Example: python scripts/crwl.py https://stripe.com\n"
            "Example: python scripts/crwl.py --seeds seeds.txt"
        )

    crawler = JobCrawler(
        seed_urls=seed_urls,
        max_pages=args.max_pages,
        request_timeout=args.timeout,
        delay=args.delay,
        concurrency=args.concurrency,
        respect_robots=args.respect_robots,
    )

    asyncio.run(crawler.crawl())
    crawler.save_results(args.output)


if __name__ == "__main__":
    main()
