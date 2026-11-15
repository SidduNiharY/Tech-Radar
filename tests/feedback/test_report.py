"""Unit tests for weekly improvement report rendering and evidence verification."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from techradar.feedback.patterns import (
    Evidence,
    PatternCandidate,
    WeightProposal,
)
from techradar.feedback.report import (
    render_feedback_report,
    render_report,
    verify_evidence,
)
from techradar.feedback.rules import Pick

WEEK = date(2026, 11, 15)
NOW = datetime(2026, 11, 15, 12, 0, 0, tzinfo=UTC)

CANDIDATE = PatternCandidate(
    kind="source",
    subject="Low quality source",
    evidence=Evidence(
        ids=[1, 2, 3],
        count=3,
        total=None,
        window_days=14,
        table="feedback",
    ),
    proposal=WeightProposal(kind="source", key="source:spam.com", target=0.5),
)

PICK = Pick(candidate_index=0, wording="Reduce content from spam.com")


def test_report_layout():
    """Verify exact formatting of weekly report with picks, automatic changes and undo."""
    text, kb = render_report(
        WEEK,
        [(1, PICK, CANDIDATE)],
        ["Lowered weight for source:spam.com"],
        tests_added=3,
    )
    assert text.startswith("🔧 Weekly improvement report\n\nChanges I suggest (tap to approve):\n")
    assert "1. Reduce content from spam.com: 3 times in 14 days" in text
    assert "• 3 bad answers saved as new tests" in text
    assert text.endswith("Undo anything: /improvements")
    assert len(kb) == 1
    assert kb[0][0].data == "rule_ok:1"
    assert kb[0][1].data == "rule_no:1"


def test_render_feedback_report_alias():
    """Verify render_feedback_report alias matches render_report."""
    text1, _ = render_report(WEEK, [(1, PICK, CANDIDATE)], [], tests_added=1)
    text2, _ = render_feedback_report(WEEK, [(1, PICK, CANDIDATE)], [], tests_added=1)
    assert text1 == text2


class FakeEvidenceSession:
    def __init__(self, count_res: int) -> None:
        self.count_res = count_res

    async def execute(self, stmt: Any) -> Any:
        class Res:
            def __init__(self, val: int) -> None:
                self.val = val

            def scalar(self) -> int:
                return self.val

        return Res(self.count_res)


async def test_verify_evidence_success_and_failure():
    """Verify evidence passes when row count matches and fails when IDs are missing."""
    session_ok = FakeEvidenceSession(3)
    assert await verify_evidence(session_ok, CANDIDATE, NOW)

    session_fail = FakeEvidenceSession(1)  # only 1 found instead of 3
    assert not await verify_evidence(session_fail, CANDIDATE, NOW)
