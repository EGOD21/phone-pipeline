from __future__ import annotations

from pathlib import Path

from .config import Settings
from .db import Database
from .filters import compliance_decision, franchise_decision, load_denylist
from .models import NormalizedBusiness, RawBusiness, SearchPartition
from .normalize import normalize_raw_business
from .providers.base import BusinessProvider
from .providers.yellowpages import YellowPagesApiProvider, YellowPagesAuthorizedScraperProvider
from .seeds import build_partitions, load_categories

ROOT = Path(__file__).resolve().parents[1]


def provider_for(source: str, settings: Settings) -> BusinessProvider:
    if source == "yp-api":
        return YellowPagesApiProvider(settings)
    if source == "yp-scraper":
        return YellowPagesAuthorizedScraperProvider(settings)
    raise ValueError(f"Unknown source: {source}")


def init_db(db: Database) -> None:
    db.init_schema(ROOT / "sql" / "schema.sql")


def discover(
    db: Database,
    states_csv: str | None,
    categories_selection: str,
    limit_cities: int | None,
    pages: int,
) -> int:
    states = {item.strip().upper() for item in states_csv.split(",")} if states_csv else None
    categories = load_categories(categories_selection)
    return db.enqueue_partitions(build_partitions(states, categories, limit_cities, pages))


def fetch(db: Database, provider: BusinessProvider, limit: int) -> tuple[int, int, int]:
    partitions = db.claim_pending_partitions(limit)
    inserted = 0
    failed = 0
    for row in partitions:
        partition = SearchPartition(
            state=row["state"], city=row["city"], category=row["category"], page=row["page"]
        )
        try:
            inserted += db.insert_raw_businesses(provider.fetch_partition(partition))
            db.mark_partition_done(row["id"])
        except Exception as exc:
            failed += 1
            db.mark_partition_failed(row["id"], str(exc))
    return inserted, failed, len(partitions)


def normalize(db: Database, limit: int) -> int:
    rows = db.pending_raw_businesses(limit)
    count = 0
    for row in rows:
        raw = RawBusiness(
            source=row["source"],
            source_ref=row["source_ref"],
            source_url=row["source_url"],
            raw_payload=row["raw_payload"],
        )
        record = normalize_raw_business(raw)
        db.insert_normalized_business(row["id"], record)
        count += 1
    return count


def dedupe(db: Database) -> int:
    return db.dedupe()


def run_franchise_filter(db: Database) -> tuple[int, int]:
    denylist = load_denylist(str(Path(__file__).parent / "data" / "franchise_denylist.txt"))
    counts = db.name_counts()
    approved = 0
    rejected = 0
    for row in db.pending_businesses():
        record = _business_from_row(row)
        state_count, city_count = counts.get(row["canonical_name"], (1, 1))
        decision = franchise_decision(record, denylist, state_count, city_count)
        if decision.approved:
            approved += 1
            continue
        rejected += 1
        db.set_business_status(row["id"], "rejected", decision.reason)
    return approved, rejected


def run_compliance_filter(db: Database) -> tuple[int, int]:
    phones, domains = db.suppressions()
    approved = 0
    rejected = 0
    for row in db.pending_businesses():
        record = _business_from_row(row)
        decision = compliance_decision(record, phones, domains)
        if decision.approved:
            approved += 1
            db.set_business_status(row["id"], "approved", None)
        else:
            rejected += 1
            db.set_business_status(row["id"], "rejected", decision.reason)
    return approved, rejected


def _business_from_row(row: dict) -> NormalizedBusiness:
    return NormalizedBusiness(
        source=row["source"],
        source_ref=row["source_ref"],
        source_url=row["source_url"],
        business_name=row["business_name"],
        category=row["category"],
        address1=row["address1"],
        city=row["city"],
        state=row["state"],
        postal_code=row["postal_code"],
        phone=row["phone"],
        website=row["website"],
        confidence_score=row["confidence_score"],
    )
