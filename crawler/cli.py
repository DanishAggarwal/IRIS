"""Command-Line Interface for IRIS PEC Document Discovery (Phase 1)."""

import argparse
import sys
from typing import Optional

from crawler.catalog import (
    get_all_sources,
    get_catalog_stats,
    get_source_by_id,
    list_discovered_documents,
    seed_default_sources,
    upsert_discovered_documents,
)
from crawler.config import SourceConfig
from crawler.engine import PECCrawlerEngine
from database.connection import SessionLocal


def cmd_seed(args: argparse.Namespace) -> int:
    """Seed the default curated PEC sources into the database."""
    session = SessionLocal()
    try:
        sources = seed_default_sources(session)
        print(f"\n[OK] Seeded {len(sources)} default PEC sources into crawler_sources:")
        for s in sources:
            print(f"  - [{s.source_id}] {s.name} ({s.url}) | Strategy: {s.strategy}")
        return 0
    finally:
        session.close()


def cmd_sources(args: argparse.Namespace) -> int:
    """Display configured PEC sources."""
    session = SessionLocal()
    try:
        sources = get_all_sources(session)
        if not sources:
            print("\nNo sources found in database. Run 'python -m crawler.cli seed' first.")
            return 0

        print(f"\nConfigured Sources ({len(sources)}):")
        print("-" * 85)
        for s in sources:
            status = "ENABLED" if s.enabled else "DISABLED"
            last_scan = s.last_scanned_at.strftime("%Y-%m-%d %H:%M:%S UTC") if s.last_scanned_at else "Never"
            print(f"ID      : {s.source_id} ({status})")
            print(f"Name    : {s.name}")
            print(f"URL     : {s.url}")
            print(f"Category: {s.category} | Strategy: {s.strategy}")
            print(f"Scanned : {last_scan}")
            print("-" * 85)
        return 0
    finally:
        session.close()


def cmd_scan(args: argparse.Namespace) -> int:
    """Execute discovery scan across configured sources without downloading files."""
    session = SessionLocal()
    try:
        if args.source:
            source = get_source_by_id(session, args.source)
            if not source:
                print(f"[ERROR] Source '{args.source}' not found.")
                return 1
            sources_to_scan = [source]
        else:
            sources_to_scan = get_all_sources(session, enabled_only=True)
            if not sources_to_scan:
                print("\nNo active sources found. Run 'python -m crawler.cli seed' first.")
                return 0

        print(f"\nInitiating IRIS PEC Document Discovery Scan across {len(sources_to_scan)} source(s)...")
        print("Note: Phase 1 discovery operates in metadata-only mode (ZERO file downloads).")
        print("=" * 85)

        engine = PECCrawlerEngine(
            timeout=args.timeout,
            request_delay=args.delay,
            max_pages_per_source=args.max_pages,
        )

        grand_total_new = 0
        grand_total_updated = 0
        grand_total_discovered = 0

        for src in sources_to_scan:
            cfg = SourceConfig(
                source_id=src.source_id,
                name=src.name,
                url=src.url,
                category=src.category,
                strategy=src.strategy,
                enabled=src.enabled,
                config=src.config or {},
            )
            print(f"\nScanning: {src.name} [{src.source_id}]")
            print(f"URL     : {src.url}")
            print(f"Strategy: {src.strategy}")

            items = engine.scan_source(cfg)
            grand_total_discovered += len(items)

            if args.dry_run:
                print(f"[DRY-RUN] Discovered {len(items)} document links (not saved to database):")
                for item in items[:5]:
                    print(f"   * {item.title} -> {item.download_url}")
                if len(items) > 5:
                    print(f"   ... and {len(items) - 5} more.")
            else:
                new_cnt, upd_cnt, chg_cnt = upsert_discovered_documents(session, src.source_id, items)
                grand_total_new += new_cnt
                grand_total_updated += upd_cnt
                print(f"Result  : {len(items)} discovered ({new_cnt} new, {upd_cnt} updated, {chg_cnt} changed).")

        print("\n" + "=" * 85)
        print("DISCOVERY SCAN SUMMARY:")
        print(f"  Total items discovered across pages : {grand_total_discovered}")
        if not args.dry_run:
            print(f"  New entries added to catalogue     : {grand_total_new}")
            print(f"  Existing entries updated timestamps: {grand_total_updated}")
            stats = get_catalog_stats(session)
            print(f"  Total catalogue document records   : {stats.get('total', 0)}")
        print("=" * 85)
        return 0
    finally:
        session.close()


def cmd_list(args: argparse.Namespace) -> int:
    """List discovered documents from persistent catalog."""
    session = SessionLocal()
    try:
        docs = list_discovered_documents(
            session,
            source_id=args.source,
            status=args.status,
            category=args.category,
            limit=args.limit,
        )
        if not docs:
            print("\nNo discovered documents matching the filter criteria.")
            return 0

        print(f"\nDiscovered Document Catalogue ({len(docs)} shown):")
        print("-" * 95)
        for d in docs:
            first_seen = d.first_discovered_at.strftime("%Y-%m-%d %H:%M")
            print(f"[{d.status.upper()}] {d.title}")
            print(f"  Category: {d.category} | Source ID: {d.source_id} | Date: {d.publication_date or 'N/A'}")
            print(f"  Download: {d.download_url}")
            print(f"  Discovered: {first_seen}")
            print("-" * 95)
        return 0
    finally:
        session.close()


def cmd_stats(args: argparse.Namespace) -> int:
    """Display catalog summary statistics."""
    session = SessionLocal()
    try:
        stats = get_catalog_stats(session)
        print("\nIRIS Discovery Catalogue Statistics:")
        print("-" * 40)
        for k, v in stats.items():
            print(f"  {k.capitalize():<18}: {v}")
        print("-" * 40)
        return 0
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crawler.cli",
        description="IRIS PEC Curated Document Discovery CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # seed
    subparsers.add_parser("seed", help="Seed default curated PEC sources into database")

    # sources
    subparsers.add_parser("sources", help="List configured PEC sources")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan configured PEC sources for document links")
    scan_parser.add_argument("--source", type=str, help="Scan only specific source by source_id")
    scan_parser.add_argument("--dry-run", action="store_true", help="Print discovered documents without DB persistence")
    scan_parser.add_argument("--timeout", type=float, default=25.0, help="HTTP request timeout in seconds")
    scan_parser.add_argument("--delay", type=float, default=0.3, help="Polite delay between requests in seconds")
    scan_parser.add_argument("--max-pages", type=int, default=10, help="Maximum archive pagination pages to follow")

    # list
    list_parser = subparsers.add_parser("list", help="List discovered document entries")
    list_parser.add_argument("--source", type=str, help="Filter by source_id")
    list_parser.add_argument("--status", type=str, help="Filter by status (e.g. discovered, approved, rejected)")
    list_parser.add_argument("--category", type=str, help="Filter by category")
    list_parser.add_argument("--limit", type=int, default=50, help="Limit number of rows displayed")

    # stats
    subparsers.add_parser("stats", help="Display discovery catalogue summary statistics")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "seed":
        return cmd_seed(args)
    elif args.subcommand == "sources":
        return cmd_sources(args)
    elif args.subcommand == "scan":
        return cmd_scan(args)
    elif args.subcommand == "list":
        return cmd_list(args)
    elif args.subcommand == "stats":
        return cmd_stats(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
