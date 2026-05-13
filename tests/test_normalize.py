from smb_phone_pipeline.models import RawBusiness
from smb_phone_pipeline.normalize import (
    clean_name,
    domain_from_url,
    normalize_phone,
    normalize_raw_business,
    normalize_url,
)


def test_normalize_phone_accepts_common_us_formats():
    assert normalize_phone("(615) 555-1212") == "+16155551212"
    assert normalize_phone("1-615-555-1212") == "+16155551212"
    assert normalize_phone("555") is None


def test_clean_name_strips_common_suffixes():
    assert clean_name("Acme Plumbing LLC") == "Acme Plumbing"
    assert clean_name("  Jane &amp; Co.  ") == "Jane"


def test_normalize_url_and_domain():
    assert normalize_url("www.example.com/") == "https://example.com"
    assert domain_from_url("https://www.example.com/about") == "example.com"


def test_normalize_raw_business_scores_source_evidence():
    raw = RawBusiness(
        source="fixture",
        source_ref="abc",
        source_url="https://source.example/listing/abc",
        raw_payload={
            "name": "Local Plumbing LLC",
            "phone": "(512) 555-0199",
            "address": "10 Main St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "website": "localplumbing.example",
        },
    )
    record = normalize_raw_business(raw)
    assert record.business_name == "Local Plumbing"
    assert record.phone == "+15125550199"
    assert record.state == "TX"
    assert record.confidence_score == 100
