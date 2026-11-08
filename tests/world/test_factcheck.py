"""Unit tests for Fact-Check claim approval gate (SEC-26)."""

import pytest

from techradar.world.factcheck import FactCheckClaim, FactCheckManager, FactCheckStatus


def test_register_claim_pending_approval() -> None:
    manager = FactCheckManager()
    claim = manager.register_claim(
        claim="RBI maintains repo rate at 6.5%",
        source_url="https://rbi.org.in/press/monetary_policy",
    )

    assert isinstance(claim, FactCheckClaim)
    assert claim.claim == "RBI maintains repo rate at 6.5%"
    assert claim.source_url == "https://rbi.org.in/press/monetary_policy"
    assert claim.status == FactCheckStatus.PENDING_APPROVAL
    assert claim.verification_notes == ""
    assert len(claim.id) > 0

    pending = manager.get_pending_claims()
    assert len(pending) == 1
    assert pending[0].id == claim.id


def test_register_claim_explicit_id() -> None:
    manager = FactCheckManager()
    claim = manager.register_claim(
        claim="India CPI inflation dips to 5.1%",
        source_url="https://mospi.gov.in/cpi",
        claim_id="custom-cpi-01",
    )
    assert claim.id == "custom-cpi-01"
    assert manager.get_claim("custom-cpi-01") is not None


def test_register_claim_empty_validation() -> None:
    manager = FactCheckManager()
    with pytest.raises(ValueError, match="Claim statement cannot be empty"):
        manager.register_claim("", "https://example.com")

    with pytest.raises(ValueError, match="Claim statement cannot be empty"):
        manager.register_claim("   ", "https://example.com")

    with pytest.raises(ValueError, match="Source URL cannot be empty"):
        manager.register_claim("Some assertion", "")

    with pytest.raises(ValueError, match="Source URL cannot be empty"):
        manager.register_claim("Some assertion", "   ")


def test_approve_claim_flow() -> None:
    manager = FactCheckManager()
    claim = manager.register_claim(
        claim="GDP growth projected at 7.2%",
        source_url="https://mospi.gov.in/gdp",
    )
    assert claim.status == FactCheckStatus.PENDING_APPROVAL

    approved = manager.approve_claim(claim.id, notes="Verified against official MoSPI release.")
    assert approved.id == claim.id
    assert approved.status == FactCheckStatus.APPROVED
    assert approved.verification_notes == "Verified against official MoSPI release."

    # Pending claims should now be empty
    assert len(manager.get_pending_claims()) == 0

    # Retrievable from manager
    retrieved = manager.get_claim(claim.id)
    assert retrieved is not None
    assert retrieved.status == FactCheckStatus.APPROVED


def test_reject_claim_flow() -> None:
    manager = FactCheckManager()
    claim = manager.register_claim(
        claim="Currency demonetized overnight",
        source_url="https://fake-news.example/article",
    )
    assert claim.status == FactCheckStatus.PENDING_APPROVAL

    rejected = manager.reject_claim(
        claim.id, reason="Debunked: No official notification from RBI or MoF."
    )
    assert rejected.id == claim.id
    assert rejected.status == FactCheckStatus.REJECTED
    assert rejected.verification_notes == "Debunked: No official notification from RBI or MoF."

    # Pending claims should now be empty
    assert len(manager.get_pending_claims()) == 0

    # Retrievable from manager
    retrieved = manager.get_claim(claim.id)
    assert retrieved is not None
    assert retrieved.status == FactCheckStatus.REJECTED


def test_get_pending_claims_filters_lifecycle() -> None:
    manager = FactCheckManager()
    c1 = manager.register_claim("Claim 1", "https://example.com/1")
    c2 = manager.register_claim("Claim 2", "https://example.com/2")
    c3 = manager.register_claim("Claim 3", "https://example.com/3")

    assert len(manager.get_pending_claims()) == 3

    manager.approve_claim(c1.id, notes="Approved")
    manager.reject_claim(c2.id, reason="Rejected")

    pending = manager.get_pending_claims()
    assert len(pending) == 1
    assert pending[0].id == c3.id


def test_missing_claim_error() -> None:
    manager = FactCheckManager()
    with pytest.raises(KeyError, match="FactCheck claim 'missing-id' not found"):
        manager.approve_claim("missing-id")

    with pytest.raises(KeyError, match="FactCheck claim 'missing-id' not found"):
        manager.reject_claim("missing-id")

    assert manager.get_claim("missing-id") is None
