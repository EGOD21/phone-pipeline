from smb_phone_pipeline.filters import (
    canonical_business_name,
    compliance_decision,
    franchise_decision,
    is_toll_free,
)
from smb_phone_pipeline.models import NormalizedBusiness


def record(**overrides):
    values = {
        "source": "fixture",
        "source_ref": "1",
        "source_url": "https://source.example/1",
        "business_name": "Elliott Family Plumbing",
        "category": "plumbers",
        "address1": "1 Main St",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78701",
        "phone": "+15125550199",
        "website": "https://elliottfamilyplumbing.example",
        "confidence_score": 100,
    }
    values.update(overrides)
    return NormalizedBusiness(**values)


def test_canonical_business_name_removes_noise():
    assert canonical_business_name("The Acme Co., LLC") == "acme"


def test_franchise_filter_rejects_known_chain():
    decision = franchise_decision(record(business_name="McDonald's"), {"mcdonald s"})
    assert not decision.approved
    assert decision.reason == "known_franchise_or_chain"


def test_franchise_filter_rejects_repeated_name_across_many_states():
    decision = franchise_decision(record(), set(), name_state_count=10, name_city_count=10)
    assert not decision.approved
    assert decision.reason == "name_repeated_across_many_states"


def test_franchise_filter_keeps_local_business():
    decision = franchise_decision(record(), set(), name_state_count=1, name_city_count=1)
    assert decision.approved


def test_compliance_filter_rejects_toll_free_and_suppressed():
    assert is_toll_free("+18005550199")
    decision = compliance_decision(record(phone="+18005550199"), set(), set())
    assert not decision.approved
    assert decision.reason == "toll_free_or_call_center_phone"

    decision = compliance_decision(record(), {"+15125550199"}, set())
    assert not decision.approved
    assert decision.reason == "suppressed_phone"


def test_compliance_filter_approves_high_confidence_main_line():
    decision = compliance_decision(record(), set(), set())
    assert decision.approved
