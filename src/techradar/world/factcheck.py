"""Fact-check approval gate module.

SEC: SEC-26 (explicit owner approval gate before unverified claims are trusted).
"""

import uuid
from enum import StrEnum

from pydantic import BaseModel, Field


class FactCheckStatus(StrEnum):
    """Fact check review approval lifecycle status."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class FactCheckClaim(BaseModel):
    """Fact check claim item subject to human approval gate."""

    id: str = Field(description="Unique claim identifier")
    claim: str = Field(description="Extracted assertion or statement text")
    source_url: str = Field(description="Originating source URL of the claim")
    status: FactCheckStatus = Field(
        default=FactCheckStatus.PENDING_APPROVAL,
        description="Current approval gate state (SEC-26)",
    )
    verification_notes: str = Field(
        default="",
        description="Reviewer notes or reason for approval / rejection",
    )


class FactCheckManager:
    """Manages fact-check claim registration and owner approval workflows (SEC-26)."""

    def __init__(self) -> None:
        self._claims: dict[str, FactCheckClaim] = {}

    def register_claim(
        self, claim: str, source_url: str, claim_id: str | None = None
    ) -> FactCheckClaim:
        """Register a new claim requiring explicit owner approval (SEC-26).

        Args:
            claim: Statement or claim text to verify.
            source_url: Source URL where the claim originated.
            claim_id: Optional explicit claim ID; generates a UUID prefix if omitted.

        Returns:
            FactCheckClaim in PENDING_APPROVAL status.

        Raises:
            ValueError: If claim or source_url is empty.
        """
        clean_claim = claim.strip()
        if not clean_claim:
            raise ValueError("Claim statement cannot be empty.")

        clean_url = source_url.strip()
        if not clean_url:
            raise ValueError("Source URL cannot be empty.")

        cid = claim_id.strip() if claim_id else uuid.uuid4().hex[:12]

        new_claim = FactCheckClaim(
            id=cid,
            claim=clean_claim,
            source_url=clean_url,
            status=FactCheckStatus.PENDING_APPROVAL,
            verification_notes="",
        )
        self._claims[cid] = new_claim
        return new_claim

    def approve_claim(self, claim_id: str, notes: str = "") -> FactCheckClaim:
        """Approve a pending claim, transitioning its status to APPROVED.

        Args:
            claim_id: Identifier of the claim to approve.
            notes: Optional verification notes or justification.

        Returns:
            Updated FactCheckClaim with APPROVED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        existing = self._claims.get(claim_id)
        if existing is None:
            raise KeyError(f"FactCheck claim '{claim_id}' not found.")

        updated = existing.model_copy(
            update={
                "status": FactCheckStatus.APPROVED,
                "verification_notes": notes.strip() or existing.verification_notes,
            }
        )
        self._claims[claim_id] = updated
        return updated

    def reject_claim(self, claim_id: str, reason: str = "") -> FactCheckClaim:
        """Reject a pending claim, transitioning its status to REJECTED.

        Args:
            claim_id: Identifier of the claim to reject.
            reason: Optional reason for rejection.

        Returns:
            Updated FactCheckClaim with REJECTED status.

        Raises:
            KeyError: If claim_id is not found.
        """
        existing = self._claims.get(claim_id)
        if existing is None:
            raise KeyError(f"FactCheck claim '{claim_id}' not found.")

        updated = existing.model_copy(
            update={
                "status": FactCheckStatus.REJECTED,
                "verification_notes": reason.strip() or existing.verification_notes,
            }
        )
        self._claims[claim_id] = updated
        return updated

    def get_pending_claims(self) -> list[FactCheckClaim]:
        """List all claims currently awaiting owner approval (SEC-26)."""
        return [c for c in self._claims.values() if c.status == FactCheckStatus.PENDING_APPROVAL]

    def get_claim(self, claim_id: str) -> FactCheckClaim | None:
        """Retrieve a claim by its ID, or None if not found."""
        return self._claims.get(claim_id)
