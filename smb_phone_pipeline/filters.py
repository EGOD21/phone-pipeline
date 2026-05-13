from __future__ import annotations

import re
from dataclasses import dataclass

from .models import NormalizedBusiness
from .normalize import domain_from_url, phone_area_code

CORPORATE_KEYWORDS = {
    "corporate",
    "headquarters",
    "hq",
    "national",
    "global",
    "enterprises",
    "holdings",
    "group",
}

NATIONAL_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "mapquest.com",
    "google.com",
}

TOLL_FREE_AREA_CODES = {"800", "833", "844", "855", "866", "877", "888"}


@dataclass(frozen=True)
class FilterDecision:
    approved: bool
    reason: str | None = None
    confidence_score: int | None = None


def canonical_business_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    value = re.sub(r"\b(the|and|inc|llc|ltd|co|corp|corporation|company)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def is_toll_free(phone: str | None) -> bool:
    return phone_area_code(phone) in TOLL_FREE_AREA_CODES


def load_denylist(path: str) -> set[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return {
            canonical_business_name(line)
            for line in handle
            if line.strip() and not line.strip().startswith("#")
        }


def franchise_decision(
    record: NormalizedBusiness,
    denylist: set[str],
    name_state_count: int = 1,
    name_city_count: int = 1,
    max_states_for_local: int = 3,
    max_cities_for_local: int = 8,
) -> FilterDecision:
    canonical = canonical_business_name(record.business_name)
    tokens = set(canonical.split())
    domain = domain_from_url(record.website)

    if not canonical:
        return FilterDecision(False, "missing_business_name")
    if canonical in denylist:
        return FilterDecision(False, "known_franchise_or_chain")
    if tokens & CORPORATE_KEYWORDS:
        return FilterDecision(False, "corporate_keyword")
    if domain in NATIONAL_DOMAINS:
        return FilterDecision(False, "non_business_or_national_profile_domain")
    if name_state_count > max_states_for_local:
        return FilterDecision(False, "name_repeated_across_many_states")
    if name_city_count > max_cities_for_local:
        return FilterDecision(False, "name_repeated_across_many_cities")
    return FilterDecision(True)


def compliance_decision(
    record: NormalizedBusiness,
    suppressed_phones: set[str],
    suppressed_domains: set[str],
    min_confidence: int = 70,
) -> FilterDecision:
    domain = domain_from_url(record.website)
    if not record.phone:
        return FilterDecision(False, "missing_or_invalid_phone", record.confidence_score)
    if record.phone in suppressed_phones:
        return FilterDecision(False, "suppressed_phone", record.confidence_score)
    if domain and domain in suppressed_domains:
        return FilterDecision(False, "suppressed_domain", record.confidence_score)
    if is_toll_free(record.phone):
        return FilterDecision(False, "toll_free_or_call_center_phone", record.confidence_score)
    if record.confidence_score < min_confidence:
        return FilterDecision(False, "low_confidence", record.confidence_score)
    return FilterDecision(True, confidence_score=record.confidence_score)
