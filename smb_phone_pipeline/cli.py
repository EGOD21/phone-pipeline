from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_settings
from .db import Database
from .quick import quick_csv_run
from .pipeline import (
    dedupe,
    discover,
    fetch,
    init_db,
    normalize,
    provider_for,
    run_compliance_filter,
    run_franchise_filter,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="smb-phone-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")

    discover_parser = subparsers.add_parser("discover")
    discover_parser.add_argument("--states")
    discover_parser.add_argument("--categories", default="all")
    discover_parser.add_argument("--limit-cities", type=int)
    discover_parser.add_argument("--pages", type=int, default=1)

    fetch_parser = subparsers.add_parser("fetch")
    fetch_parser.add_argument("--source", choices=["yp-api", "yp-scraper"], default="yp-api")
    fetch_parser.add_argument("--limit", type=int, default=100)

    normalize_parser = subparsers.add_parser("normalize")
    normalize_parser.add_argument("--limit", type=int, default=1000)

    subparsers.add_parser("dedupe")
    subparsers.add_parser("franchise-filter")
    subparsers.add_parser("compliance-filter")

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--csv")
    export_parser.add_argument("--jsonl")

    simple_seed_parser = subparsers.add_parser("simple-seed")
    simple_seed_parser.add_argument("--states")
    simple_seed_parser.add_argument("--categories", default="all")
    simple_seed_parser.add_argument("--pages", type=int, default=1)

    simple_run_parser = subparsers.add_parser("simple-run")
    simple_run_parser.add_argument("--source", choices=["yp-api", "yp-scraper"], default="yp-api")
    simple_run_parser.add_argument("--batch-size", type=int, default=100)
    simple_run_parser.add_argument("--normalize-limit", type=int, default=5000)
    simple_run_parser.add_argument("--export-csv", default="out/approved.csv")
    simple_run_parser.add_argument("--export-jsonl", default="out/approved.jsonl")
    simple_run_parser.add_argument("--max-batches", type=int)

    quick_parser = subparsers.add_parser("quick-csv")
    quick_parser.add_argument("--source", choices=["yp-api", "yp-scraper"], default="yp-api")
    quick_parser.add_argument("--states")
    quick_parser.add_argument("--categories", default="all")
    quick_parser.add_argument("--limit-cities", type=int, default=1)
    quick_parser.add_argument("--pages", type=int, default=1)
    quick_parser.add_argument("--max-searches", type=int)
    quick_parser.add_argument("--csv", default="out/approved.csv")
    quick_parser.add_argument("--jsonl", default="out/approved.jsonl")
    quick_parser.add_argument("--timeout", type=int, default=10)

    run_all_parser = subparsers.add_parser("run-all")
    run_all_parser.add_argument("--source", choices=["yp-api", "yp-scraper"], default="yp-api")
    run_all_parser.add_argument("--states")
    run_all_parser.add_argument("--categories", default="all")
    run_all_parser.add_argument("--limit-cities", type=int, default=1)
    run_all_parser.add_argument("--pages", type=int, default=1)
    run_all_parser.add_argument("--fetch-limit", type=int, default=100)
    run_all_parser.add_argument("--normalize-limit", type=int, default=1000)
    run_all_parser.add_argument("--export-csv")
    run_all_parser.add_argument("--export-jsonl")

    args = parser.parse_args()
    settings = load_settings()
    db = Database(settings.database_url)

    if args.command == "init-db":
        init_db(db)
        print("initialized database schema")
    elif args.command == "discover":
        inserted = discover(db, args.states, args.categories, args.limit_cities, args.pages)
        print(f"enqueued {inserted} new partitions")
    elif args.command == "fetch":
        inserted, failed, processed = fetch(db, provider_for(args.source, settings), args.limit)
        print(f"processed {processed} partitions; inserted {inserted} raw businesses; failed {failed} partitions")
    elif args.command == "normalize":
        count = normalize(db, args.limit)
        print(f"normalized {count} raw businesses")
    elif args.command == "dedupe":
        count = dedupe(db)
        print(f"rejected {count} duplicate businesses")
    elif args.command == "franchise-filter":
        kept, rejected = run_franchise_filter(db)
        print(f"franchise filter kept {kept} pending; rejected {rejected}")
    elif args.command == "compliance-filter":
        approved, rejected = run_compliance_filter(db)
        print(f"compliance filter approved {approved}; rejected {rejected}")
    elif args.command == "export":
        count = db.export_approved(
            Path(args.csv) if args.csv else None,
            Path(args.jsonl) if args.jsonl else None,
        )
        print(f"exported {count} approved businesses")
    elif args.command == "simple-seed":
        init_db(db)
        inserted = discover(db, args.states, args.categories, None, args.pages)
        counts = db.partition_counts()
        print(f"seeded {inserted} new search jobs; queue={counts}")
    elif args.command == "simple-run":
        init_db(db)
        provider = provider_for(args.source, settings)
        totals = {
            "processed": 0,
            "raw_inserted": 0,
            "failed": 0,
            "normalized": 0,
            "duplicates": 0,
            "franchise_rejected": 0,
            "approved": 0,
            "compliance_rejected": 0,
        }
        batch = 0
        while True:
            if args.max_batches is not None and batch >= args.max_batches:
                break
            inserted, failed, processed = fetch(db, provider, args.batch_size)
            normalized = normalize(db, args.normalize_limit)
            duplicates = dedupe(db)
            _, franchise_rejected = run_franchise_filter(db)
            approved, compliance_rejected = run_compliance_filter(db)
            totals["processed"] += processed
            totals["raw_inserted"] += inserted
            totals["failed"] += failed
            totals["normalized"] += normalized
            totals["duplicates"] += duplicates
            totals["franchise_rejected"] += franchise_rejected
            totals["approved"] += approved
            totals["compliance_rejected"] += compliance_rejected
            batch += 1
            print(
                f"batch {batch}: processed={processed} raw_inserted={inserted} "
                f"failed={failed} normalized={normalized} approved={approved}"
            )
            if processed == 0 and db.raw_pending_count() == 0:
                break
        exported = db.export_approved(Path(args.export_csv), Path(args.export_jsonl))
        counts = db.partition_counts()
        print(f"simple run complete: totals={totals} exported={exported} queue={counts}")
    elif args.command == "quick-csv":
        settings = type(settings)(**{**settings.__dict__, "yp_api_timeout_seconds": args.timeout})
        searched, written, rejected = quick_csv_run(
            settings=settings,
            source=args.source,
            states_csv=args.states,
            categories_selection=args.categories,
            limit_cities=args.limit_cities,
            pages=args.pages,
            max_searches=args.max_searches,
            csv_path=Path(args.csv),
            jsonl_path=Path(args.jsonl) if args.jsonl else None,
        )
        print(f"quick csv complete: searched={searched} written={written} rejected={rejected} csv={args.csv}")
    elif args.command == "run-all":
        init_db(db)
        enqueued = discover(db, args.states, args.categories, args.limit_cities, args.pages)
        inserted, failed, processed = fetch(db, provider_for(args.source, settings), args.fetch_limit)
        normalized = normalize(db, args.normalize_limit)
        duplicates = dedupe(db)
        _, franchise_rejected = run_franchise_filter(db)
        approved, compliance_rejected = run_compliance_filter(db)
        exported = db.export_approved(
            Path(args.export_csv) if args.export_csv else None,
            Path(args.export_jsonl) if args.export_jsonl else None,
        )
        print(
            "run complete: "
            f"enqueued={enqueued} fetch_processed={processed} raw_inserted={inserted} fetch_failed={failed} "
            f"normalized={normalized} duplicates={duplicates} "
            f"franchise_rejected={franchise_rejected} "
            f"approved={approved} compliance_rejected={compliance_rejected} exported={exported}"
        )


if __name__ == "__main__":
    main()
