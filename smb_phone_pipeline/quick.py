from __future__ import annotations

import csv
import json
from pathlib import Path

from .config import Settings
from .filters import compliance_decision, franchise_decision, load_denylist
from .normalize import normalize_raw_business
from .pipeline import provider_for
from .seeds import build_partitions, load_categories


def quick_csv_run(
    settings: Settings,
    source: str,
    states_csv: str | None,
    categories_selection: str,
    limit_cities: int | None,
    pages: int,
    max_searches: int | None,
    csv_path: Path,
    jsonl_path: Path | None,
) -> tuple[int, int, int]:
    states = {item.strip().upper() for item in states_csv.split(",")} if states_csv else None
    categories = load_categories(categories_selection)
    partitions = build_partitions(states, categories, limit_cities, pages)
    if max_searches is not None:
        partitions = partitions[:max_searches]

    provider = provider_for(source, settings)
    denylist = load_denylist(str(Path(__file__).parent / "data" / "franchise_denylist.txt"))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if jsonl_path:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    seen_phones: set[str] = set()
    written = 0
    rejected = 0
    searched = 0
    rejection_reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        nonlocal rejected
        rejected += 1
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    fieldnames = [
        "business_name", "category", "address1", "city", "state", "postal_code",
        "phone", "website", "confidence_score", "source", "source_ref", "source_url",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as csv_handle:
        writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
        writer.writeheader()
        jsonl_handle = jsonl_path.open("w", encoding="utf-8") if jsonl_path else None
        try:
            for partition in partitions:
                searched += 1
                print(f"search {searched}/{len(partitions)}: {partition.category} in {partition.city}, {partition.state}")
                try:
                    raw_rows = provider.fetch_partition(partition)
                except Exception as exc:
                    reject(type(exc).__name__)
                    print(f"  skipped: {type(exc).__name__}: {exc}")
                    continue
                for raw in raw_rows:
                    record = normalize_raw_business(raw)
                    franchise = franchise_decision(record, denylist)
                    compliance = compliance_decision(record, set(), set())
                    if not franchise.approved:
                        reject(franchise.reason or "franchise_rejected")
                        continue
                    if not compliance.approved:
                        reject(compliance.reason or "compliance_rejected")
                        continue
                    if not record.phone:
                        reject("missing_phone")
                        continue
                    if record.phone in seen_phones:
                        reject("duplicate_phone")
                        continue
                    seen_phones.add(record.phone)
                    row = {name: getattr(record, name) for name in fieldnames}
                    writer.writerow(row)
                    if jsonl_handle:
                        jsonl_handle.write(json.dumps(row, sort_keys=True) + "\n")
                    written += 1
        finally:
            if jsonl_handle:
                jsonl_handle.close()
    print(f"rejection reasons: {rejection_reasons}")
    return searched, written, rejected
