from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchPartition:
    state: str
    city: str
    category: str
    page: int = 1


@dataclass(frozen=True)
class RawBusiness:
    source: str
    source_ref: str
    source_url: str | None
    raw_payload: dict


@dataclass(frozen=True)
class NormalizedBusiness:
    source: str
    source_ref: str
    source_url: str | None
    business_name: str
    category: str | None
    address1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    phone: str | None
    website: str | None
    confidence_score: int
