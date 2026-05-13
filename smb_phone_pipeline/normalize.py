from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import NormalizedBusiness, RawBusiness

NON_DIGIT_RE = re.compile(r"\D+")
MULTISPACE_RE = re.compile(r"\s+")


def clean_name(value: str | None) -> str:
    if not value:
        return ""
    value = MULTISPACE_RE.sub(" ", value.replace("&amp;", "&")).strip(" ,.-")
    value = re.sub(r"\s*&\s*(co|company)\.?$", "", value, flags=re.I)
    value = re.sub(r"\b(inc|llc|ltd|co|corp|corporation)\.?$", "", value, flags=re.I)
    value = value.strip(" ,.-")
    return value


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = NON_DIGIT_RE.sub("", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"+1{digits}"


def phone_area_code(phone: str | None) -> str | None:
    if not phone or not phone.startswith("+1") or len(phone) != 12:
        return None
    return phone[2:5]


def normalize_url(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    if not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return f"{parsed.scheme.lower()}://{host}{parsed.path.rstrip('/')}"


def domain_from_url(value: str | None) -> str | None:
    normalized = normalize_url(value)
    if not normalized:
        return None
    return urlparse(normalized).netloc


def normalize_state(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().upper()
    return value if len(value) == 2 else None


def confidence_for(record: NormalizedBusiness) -> int:
    score = 0
    if record.business_name:
        score += 25
    if record.phone:
        score += 30
    if record.address1 and record.city and record.state:
        score += 25
    if record.source_url or record.source_ref:
        score += 10
    if record.website:
        score += 10
    return min(score, 100)


def normalize_raw_business(raw: RawBusiness) -> NormalizedBusiness:
    payload = raw.raw_payload
    name = clean_name(
        payload.get("business_name")
        or payload.get("name")
        or payload.get("title")
        or payload.get("listingName")
    )
    phone = normalize_phone(payload.get("phone") or payload.get("phone_number"))
    record = NormalizedBusiness(
        source=raw.source,
        source_ref=raw.source_ref,
        source_url=raw.source_url,
        business_name=name,
        category=payload.get("category") or payload.get("primary_category") or payload.get("categories"),
        address1=(
            payload.get("address1")
            or payload.get("street")
            or payload.get("street_address")
            or payload.get("address")
        ),
        city=payload.get("city") or payload.get("locality"),
        state=normalize_state(payload.get("state") or payload.get("region")),
        postal_code=payload.get("postal_code") or payload.get("zip") or payload.get("zipcode"),
        phone=phone,
        website=normalize_url(payload.get("website") or payload.get("website_url") or payload.get("url")),
        confidence_score=0,
    )
    return NormalizedBusiness(**{**record.__dict__, "confidence_score": confidence_for(record)})
