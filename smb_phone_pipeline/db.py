from __future__ import annotations

import csv
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .filters import canonical_business_name
from .models import NormalizedBusiness, RawBusiness, SearchPartition
from .normalize import domain_from_url


class Database:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def connect(self) -> Iterator[object]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Missing Postgres dependency. Run: pip install -e '.[dev]'"
            ) from exc
        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            yield conn

    def init_schema(self, schema_path: Path) -> None:
        with self.connect() as conn:
            conn.execute(schema_path.read_text(encoding="utf-8"))

    def enqueue_partitions(self, partitions: list[SearchPartition]) -> int:
        if not partitions:
            return 0
        with self.connect() as conn:
            before = conn.execute("SELECT count(*) AS count FROM search_partitions").fetchone()[
                "count"
            ]
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO search_partitions (state, city, category, page)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    [(p.state, p.city, p.category, p.page) for p in partitions],
                )
            after = conn.execute("SELECT count(*) AS count FROM search_partitions").fetchone()[
                "count"
            ]
        return after - before

    def claim_pending_partitions(self, limit: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                UPDATE search_partitions
                   SET status = 'running', attempts = attempts + 1, updated_at = now()
                 WHERE id IN (
                   SELECT id
                     FROM search_partitions
                    WHERE status IN ('pending', 'failed')
                    ORDER BY id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                 )
                RETURNING *
                """,
                (limit,),
            ).fetchall()
            return list(rows)

    def mark_partition_done(self, partition_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE search_partitions
                   SET status = 'done', last_error = NULL, updated_at = now()
                 WHERE id = %s
                """,
                (partition_id,),
            )

    def mark_partition_failed(self, partition_id: int, error: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE search_partitions
                   SET status = 'failed', last_error = %s, updated_at = now()
                 WHERE id = %s
                """,
                (error[:1000], partition_id),
            )

    def insert_raw_businesses(self, rows: list[RawBusiness]) -> int:
        if not rows:
            return 0
        from psycopg.types.json import Jsonb

        with self.connect() as conn:
            before = conn.execute("SELECT count(*) AS count FROM raw_businesses").fetchone()[
                "count"
            ]
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO raw_businesses (source, source_ref, source_url, raw_payload)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    [
                        (row.source, row.source_ref, row.source_url, Jsonb(row.raw_payload))
                        for row in rows
                    ],
                )
            after = conn.execute("SELECT count(*) AS count FROM raw_businesses").fetchone()[
                "count"
            ]
        return after - before

    def pending_raw_businesses(self, limit: int) -> list[dict]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT *
                      FROM raw_businesses
                     WHERE normalized = false
                     ORDER BY id
                     LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )

    def insert_normalized_business(self, raw_id: int, record: NormalizedBusiness) -> None:
        canonical = canonical_business_name(record.business_name)
        domain = domain_from_url(record.website)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO businesses (
                  raw_business_id, source, source_ref, source_url, business_name, canonical_name,
                  category, address1, city, state, postal_code, phone, website, website_domain,
                  confidence_score
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source, source_ref) DO UPDATE SET
                  source_url = excluded.source_url,
                  business_name = excluded.business_name,
                  canonical_name = excluded.canonical_name,
                  category = excluded.category,
                  address1 = excluded.address1,
                  city = excluded.city,
                  state = excluded.state,
                  postal_code = excluded.postal_code,
                  phone = excluded.phone,
                  website = excluded.website,
                  website_domain = excluded.website_domain,
                  confidence_score = excluded.confidence_score,
                  updated_at = now()
                """,
                (
                    raw_id,
                    record.source,
                    record.source_ref,
                    record.source_url,
                    record.business_name,
                    canonical,
                    record.category,
                    record.address1,
                    record.city,
                    record.state,
                    record.postal_code,
                    record.phone,
                    record.website,
                    domain,
                    record.confidence_score,
                ),
            )
            conn.execute("UPDATE raw_businesses SET normalized = true WHERE id = %s", (raw_id,))

    def dedupe(self) -> int:
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH ranked AS (
                  SELECT id,
                         first_value(id) OVER (
                           PARTITION BY coalesce(phone, ''), canonical_name, coalesce(postal_code, '')
                           ORDER BY confidence_score DESC, id ASC
                         ) AS keeper_id
                    FROM businesses
                   WHERE status = 'pending'
                     AND phone IS NOT NULL
                     AND canonical_name <> ''
                )
                UPDATE businesses b
                   SET duplicate_of = ranked.keeper_id,
                       status = 'rejected',
                       rejection_reason = 'duplicate_business',
                       updated_at = now()
                  FROM ranked
                 WHERE b.id = ranked.id
                   AND ranked.id <> ranked.keeper_id
                RETURNING b.id
                """
            ).fetchall()
            return len(rows)

    def name_counts(self) -> dict[str, tuple[int, int]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT canonical_name,
                       count(DISTINCT state) AS states,
                       count(DISTINCT city || ',' || state) AS cities
                  FROM businesses
                 WHERE status = 'pending'
                 GROUP BY canonical_name
                """
            ).fetchall()
        return {row["canonical_name"]: (row["states"], row["cities"]) for row in rows}

    def pending_businesses(self) -> list[dict]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT *
                      FROM businesses
                     WHERE status = 'pending'
                     ORDER BY id
                    """
                ).fetchall()
            )

    def set_business_status(self, business_id: int, status: str, reason: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE businesses
                   SET status = %s, rejection_reason = %s, updated_at = now()
                 WHERE id = %s
                """,
                (status, reason, business_id),
            )

    def suppressions(self) -> tuple[set[str], set[str]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT type, value FROM suppressions").fetchall()
        phones = {row["value"] for row in rows if row["type"] == "phone"}
        domains = {row["value"] for row in rows if row["type"] == "domain"}
        return phones, domains

    def partition_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, count(*) AS count
                  FROM search_partitions
                 GROUP BY status
                """
            ).fetchall()
        return {row["status"]: row["count"] for row in rows}

    def raw_pending_count(self) -> int:
        with self.connect() as conn:
            return conn.execute(
                "SELECT count(*) AS count FROM raw_businesses WHERE normalized = false"
            ).fetchone()["count"]

    def export_approved(self, csv_path: Path | None, jsonl_path: Path | None) -> int:
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    """
                    SELECT business_name, category, address1, city, state, postal_code, phone,
                           website, confidence_score, source, source_ref, source_url
                      FROM businesses
                     WHERE status = 'approved'
                     ORDER BY state, city, business_name
                    """
                ).fetchall()
            )

        if csv_path:
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else [])
                if rows:
                    writer.writeheader()
                    writer.writerows(rows)
        if jsonl_path:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with jsonl_path.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
        return len(rows)
