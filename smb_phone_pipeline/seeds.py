from __future__ import annotations

import csv
from pathlib import Path

from .models import SearchPartition

DATA_DIR = Path(__file__).parent / "data"


def load_categories(selection: str) -> list[str]:
    if selection != "all":
        return [item.strip() for item in selection.split(",") if item.strip()]
    path = DATA_DIR / "categories.txt"
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def load_seed_cities(states: set[str] | None, limit_per_state: int | None) -> list[tuple[str, str]]:
    path = DATA_DIR / "seed_cities.csv"
    counts: dict[str, int] = {}
    cities: list[tuple[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            state = row["state"].upper()
            if states and state not in states:
                continue
            if limit_per_state is not None and counts.get(state, 0) >= limit_per_state:
                continue
            cities.append((state, row["city"]))
            counts[state] = counts.get(state, 0) + 1
    return cities


def build_partitions(
    states: set[str] | None,
    categories: list[str],
    limit_cities: int | None,
    pages: int,
) -> list[SearchPartition]:
    partitions: list[SearchPartition] = []
    for state, city in load_seed_cities(states, limit_cities):
        for category in categories:
            for page in range(1, pages + 1):
                partitions.append(SearchPartition(state=state, city=city, category=category, page=page))
    return partitions
