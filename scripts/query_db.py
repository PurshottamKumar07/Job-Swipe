"""
Database Query CLI
==================
Quick command-line interface to inspect the crwlr database.

Usage:
    python scripts/query_db.py stats
    python scripts/query_db.py runs
    python scripts/query_db.py links [--run ID] [--limit N]
    python scripts/query_db.py jobs  [--company NAME] [--method METHOD] [--remote] [--min-salary N] [--limit N]
    python scripts/query_db.py search "python developer" [--remote] [--min-salary N]
"""

import os
import sys
import json
import argparse

# Ensure project root is in sys.path for standalone script execution
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.db import Database


def _pretty(data):
    """Pretty-print a dict or list as JSON."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cmd_stats(db: Database, _args):
    print(f"\n{'=' * 50}")
    print(f"  crwlr Database Stats")
    print(f"  {db.db_path}")
    print(f"{'=' * 50}")
    stats = db.get_stats()
    print(f"  Crawl runs       : {stats['total_crawl_runs']}")
    print(f"  Job links        : {stats['total_job_links']}")
    print(f"  Extracted jobs   : {stats['total_extracted_jobs']}")
    print(f"  Active jobs      : {stats.get('active_jobs', 0)}")
    print(f"  Remote jobs      : {stats.get('remote_jobs', 0)}")
    print(f"  Unique companies : {stats['unique_companies']}")
    if stats.get("by_method"):
        print(f"\n  By extraction method:")
        for method, count in stats["by_method"].items():
            print(f"    {method:<22} : {count}")
    if stats.get("top_companies"):
        print(f"\n  Top companies:")
        for company, count in stats["top_companies"].items():
            print(f"    {company:<30} : {count}")
    print(f"{'=' * 50}\n")


def cmd_runs(db: Database, _args):
    runs = db.get_all_crawl_runs()
    if not runs:
        print("No crawl runs found.")
        return
    print(f"\n{'=' * 70}")
    print(f"  {'ID':<5} {'Type':<10} {'Status':<12} {'Pages':<8} {'Links':<8} {'Errors':<8} {'Started'}")
    print(f"  {'-'*5} {'-'*10} {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*24}")
    for r in runs:
        print(
            f"  {r['id']:<5} {r['run_type']:<10} {r['status']:<12} "
            f"{r['pages_crawled'] or 0:<8} {r['links_inspected'] or 0:<8} "
            f"{r['errors'] or 0:<8} {r['started_at']}"
        )
    print(f"{'=' * 70}\n")

def cmd_links(db: Database, args):
    links = db.get_job_links(crawl_run_id=args.run, limit=args.limit)
    if not links:
        print("No job links found.")
        return
    for link in links:
        print(f"  [{link['id']}] {link['url']}")
        print(f"        reason: {link['match_reason']}  |  found on: {link['found_on']}")
        print()


def cmd_jobs(db: Database, args):
    jobs = db.get_extracted_jobs(
        company=args.company,
        method=args.method,
        is_remote=args.remote if args.remote else None,
        min_salary=args.min_salary,
        active_only=not args.all,
        limit=args.limit,
    )
    if not jobs:
        print("No extracted jobs found.")
        return
    for j in jobs:
        remote_tag = " [REMOTE]" if j.get("is_remote") else ""
        salary_str = j.get("salary") or (
            f"${j['salary_min']:,.0f}-${j['salary_max']:,.0f}" if j.get("salary_min") else "—"
        )
        print(f"  [{j['id']}] {j['title'] or '(no title)'}{remote_tag}")
        print(f"        company  : {j['company'] or '—'}")
        print(f"        location : {j['location'] or '—'}")
        print(f"        salary   : {salary_str}")
        print(f"        method   : {j['extraction_method']}")
        print(f"        url      : {j['source_url']}")
        print()


def cmd_search(db: Database, args):
    query = " ".join(args.query)
    jobs = db.search_jobs(
        query,
        limit=args.limit,
        is_remote=args.remote if args.remote else None,
        min_salary=args.min_salary,
        active_only=not args.all,
    )
    if not jobs:
        print(f"No jobs matching '{query}'.")
        return
    print(f"\n  Found {len(jobs)} result(s) for '{query}':\n")
    for j in jobs:
        remote_tag = " [REMOTE]" if j.get("is_remote") else ""
        salary_str = j.get("salary") or (
            f"${j['salary_min']:,.0f}-${j['salary_max']:,.0f}" if j.get("salary_min") else "—"
        )
        print(f"  [{j['id']}] {j['title'] or '(no title)'}{remote_tag}")
        print(f"        company  : {j['company'] or '—'}")
        print(f"        location : {j['location'] or '—'}")
        print(f"        salary   : {salary_str}")
        print(f"        url      : {j['source_url']}")
        print()


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Query the crwlr SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stats", help="Show database statistics.")
    sub.add_parser("runs",  help="List all crawl/extract runs.")

    p_links = sub.add_parser("links", help="List discovered job links.")
    p_links.add_argument("--run",   type=int, default=None, help="Filter by crawl run ID.")
    p_links.add_argument("--limit", type=int, default=50,   help="Max results (default: 50).")

    p_jobs = sub.add_parser("jobs", help="List extracted jobs.")
    p_jobs.add_argument("--company",    type=str,   default=None, help="Filter by company name.")
    p_jobs.add_argument("--method",     type=str,   default=None, help="Filter by extraction method.")
    p_jobs.add_argument("--remote",     action="store_true",      help="Only show remote jobs.")
    p_jobs.add_argument("--min-salary", type=float, default=None, help="Minimum salary threshold.")
    p_jobs.add_argument("--all",        action="store_true",      help="Include inactive/expired jobs.")
    p_jobs.add_argument("--limit",      type=int,   default=50,   help="Max results (default: 50).")

    p_search = sub.add_parser("search", help="Search jobs by keyword.")
    p_search.add_argument("query",        nargs="+",                help="Search terms.")
    p_search.add_argument("--remote",     action="store_true",      help="Only show remote jobs.")
    p_search.add_argument("--min-salary", type=float, default=None, help="Minimum salary threshold.")
    p_search.add_argument("--all",        action="store_true",      help="Include inactive/expired jobs.")
    p_search.add_argument("--limit",      type=int,   default=50,   help="Max results (default: 50).")

    args = parser.parse_args()
    db = Database()

    {
        "stats":  cmd_stats,
        "runs":   cmd_runs,
        "links":  cmd_links,
        "jobs":   cmd_jobs,
        "search": cmd_search,
    }[args.command](db, args)

    db.close()


if __name__ == "__main__":
    main()
