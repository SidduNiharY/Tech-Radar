from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from evals.mcq.export import render_review_markdown
from techradar.db.models import MCQ
from techradar.practice.mcq import (
    CHAPTER_MCQ_SYSTEM,
    CHECK_SYSTEM,
    MCQ_SYSTEM,
    CheckerPick,
    ChunkRow,
    FactRow,
    MCQDraft,
    make_chapter_mcq,
    make_mcq,
    run_make_mcqs,
    shuffle_options,
)
from tests.fakes import FakeCompleter

VERIFIED_FACT_5_5 = FactRow(
    id=42,
    statement="RBI policy repo rate is currently 5.5%",
    subject="repo rate",
    value="5.5%",
    status="verified",
    section="economy",
)

CHUNK_SAYING_CRR_IS_4_PERCENT = ChunkRow(
    id=101,
    chapter_id=12,
    text="Under current statutory norms, the Cash Reserve Ratio (CRR) is 4% for scheduled banks.",
    flagged=False,
)

FLAGGED_CHUNK = ChunkRow(
    id=102,
    chapter_id=12,
    text="Some sensitive or flagged unvetted content here.",
    flagged=True,
)

SAMPLE_DRAFT = MCQDraft(
    question="What is the official policy repo rate fixed by RBI?",
    options=["5.5%", "5.0%", "6.0%", "6.5%"],
    answer_index=0,
    explanation="The policy repo rate is currently 5.5%.",
)


def test_mcq_draft_valid():
    draft = MCQDraft(
        question="What is the capital of India?",
        options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        answer_index=1,
        explanation="New Delhi is the official capital of India.",
    )
    assert draft.question == "What is the capital of India?"
    assert len(draft.options) == 4
    assert draft.answer_index == 1
    assert draft.explanation == "New Delhi is the official capital of India."


def test_mcq_draft_rejects_fewer_than_four_options():
    with pytest.raises(ValidationError, match="4"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata"],
            answer_index=1,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_more_than_four_options():
    with pytest.raises(ValidationError, match="4"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai", "Bengaluru"],
            answer_index=1,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_non_unique_options():
    with pytest.raises(ValidationError, match="unique"):
        MCQDraft(
            question="What is the capital of India?",
            options=["New Delhi", "New Delhi", "Kolkata", "Chennai"],
            answer_index=0,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_invalid_answer_index():
    with pytest.raises(ValidationError):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=-1,
            explanation="Explanation text here.",
        )

    with pytest.raises(ValidationError):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=4,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_question_length_boundaries():
    with pytest.raises(ValidationError):
        MCQDraft(
            question="Short?",
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Explanation text here.",
        )

    with pytest.raises(ValidationError):
        MCQDraft(
            question="Q" * 301,
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Explanation text here.",
        )


def test_mcq_draft_rejects_links():
    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="Visit https://example.com for the question?",
            options=["A", "B", "C", "D"],
            answer_index=0,
            explanation="Valid explanation.",
        )

    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="What is the official URL?",
            options=["https://example.com", "Option B", "Option C", "Option D"],
            answer_index=0,
            explanation="Valid explanation.",
        )

    with pytest.raises(ValidationError, match="links are not allowed"):
        MCQDraft(
            question="What is the capital of India?",
            options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
            answer_index=1,
            explanation="Check out http://rbi.org.in for info.",
        )


async def test_unverified_fact_makes_no_call():
    fc = FakeCompleter([])
    fact = FactRow(
        id=1,
        statement="s",
        subject="x",
        value="5.5%",
        status="unverified",
        section="economy",
    )
    assert await make_mcq(fc, fact) is None
    assert fc.calls == []


async def test_correct_option_must_contain_value():
    draft = MCQDraft(
        question="What is the current policy repo rate?",
        options=["4%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="Repo rate explanation.",
    )
    fc = FakeCompleter([draft.model_dump_json()])
    assert await make_mcq(fc, VERIFIED_FACT_5_5) is None


async def test_checker_disagreement_drops_mcq():
    draft = MCQDraft(
        question="What is the current policy repo rate?",
        options=["5.5%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="Repo rate explanation.",
    )
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 2}'])
    assert await make_mcq(fc, VERIFIED_FACT_5_5) is None


async def test_checker_agreement_returns_shuffled_draft():
    draft = MCQDraft(
        question="What is the current policy repo rate?",
        options=["5.5%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="Repo rate explanation.",
    )
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 0}'])
    d = await make_mcq(fc, VERIFIED_FACT_5_5)
    assert d is not None
    assert d.options[d.answer_index] == "5.5%"


def test_shuffle_is_deterministic_and_tracks_key():
    a = shuffle_options(SAMPLE_DRAFT, 7)
    b = shuffle_options(SAMPLE_DRAFT, 7)
    assert a == b
    assert a.options[a.answer_index] == SAMPLE_DRAFT.options[SAMPLE_DRAFT.answer_index]
    assert set(a.options) == set(SAMPLE_DRAFT.options)


async def test_chapter_mcq_needs_exact_quote():
    draft = MCQDraft(
        question="What is the statutory Cash Reserve Ratio?",
        options=["9%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="CRR explanation.",
        answer_quote="CRR is 9%",
    )
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 0}'])
    assert await make_chapter_mcq(fc, CHUNK_SAYING_CRR_IS_4_PERCENT) is None


async def test_flagged_chunk_makes_no_call():
    fc = FakeCompleter([])
    assert await make_chapter_mcq(fc, FLAGGED_CHUNK) is None
    assert fc.calls == []


async def test_chapter_mcq_success():
    draft = MCQDraft(
        question="What is the Cash Reserve Ratio for scheduled banks?",
        options=["4%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="The Cash Reserve Ratio (CRR) is 4%.",
        answer_quote="Cash Reserve Ratio (CRR) is 4%",
    )
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 0}'])
    res = await make_chapter_mcq(fc, CHUNK_SAYING_CRR_IS_4_PERCENT)
    assert res is not None
    assert res.options[res.answer_index] == "4%"


async def test_chapter_mcq_rejects_missing_option_words_in_quote():
    draft = MCQDraft(
        question="What is the policy repo rate?",
        options=["6.5%", "5%", "6%", "7%"],
        answer_index=0,
        explanation="Repo rate explanation.",
        answer_quote="Cash Reserve Ratio (CRR) is 4%",
    )
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 0}'])
    assert await make_chapter_mcq(fc, CHUNK_SAYING_CRR_IS_4_PERCENT) is None


async def test_indian_languages_preserved_in_mcq():
    # Hindi fact test
    draft_hi = MCQDraft(
        question="भारत की राजधानी कौन सी है?",
        options=["नई दिल्ली", "मुंबई", "कोलकाता", "चेन्नई"],
        answer_index=0,
        explanation="नई दिल्ली भारत की आधिकारिक राजधानी है।",
    )
    fc_hi = FakeCompleter([draft_hi.model_dump_json(), '{"answer_index": 0}'])
    fact_hi = FactRow(
        id=201,
        statement="भारत की राजधानी नई दिल्ली है।",
        subject="राजधानी",
        value="नई दिल्ली",
        status="verified",
        section="india",
    )
    res_hi = await make_mcq(fc_hi, fact_hi)
    assert res_hi is not None
    assert res_hi.options[res_hi.answer_index] == "नई दिल्ली"
    assert "नई दिल्ली" in res_hi.explanation
    assert res_hi.question == "भारत की राजधानी कौन सी है?"

    # Telugu chapter test
    draft_te = MCQDraft(
        question="ఆంధ్రప్రదేశ్ రాష్ట్రం యొక్క రాజధాని ఏది?",
        options=["అమరావతి", "విశాఖపట్నం", "హైదరాబాద్", "కర్నూలు"],
        answer_index=0,
        explanation="ఆంధ్రప్రదేశ్ రాష్ట్రం యొక్క రాజధాని అమరావతి.",
        answer_quote="రాజధాని అమరావతి",
    )
    fc_te = FakeCompleter([draft_te.model_dump_json(), '{"answer_index": 0}'])
    chunk_te = ChunkRow(
        id=202,
        chapter_id=4,
        text="ఆంధ్రప్రదేశ్ రాష్ట్రం యొక్క రాజధాని అమరావతి అని ప్రకటించారు.",
        flagged=False,
    )
    res_te = await make_chapter_mcq(fc_te, chunk_te)
    assert res_te is not None
    assert res_te.options[res_te.answer_index] == "అమరావతి"
    assert "అమరావతి" in res_te.explanation
    assert res_te.question == "ఆంధ్రప్రదేశ్ రాష్ట్రం యొక్క రాజధాని ఏది?"


def test_prompt_constants():
    assert "Indian competitive-exam" in MCQ_SYSTEM
    assert "UNTRUSTED" in MCQ_SYSTEM
    assert "0-based index" in CHECK_SYSTEM
    assert "passage" in CHAPTER_MCQ_SYSTEM
    assert "fact" not in CHAPTER_MCQ_SYSTEM


def test_checker_pick_validation():
    pick = CheckerPick(answer_index=2)
    assert pick.answer_index == 2

    with pytest.raises(ValidationError):
        CheckerPick(answer_index=4)

    with pytest.raises(ValidationError):
        CheckerPick(answer_index=-1)


async def test_run_make_mcqs_job_body():
    now = datetime(2026, 11, 15, 5, 30, tzinfo=UTC)
    mock_session = AsyncMock()
    mock_session.add = MagicMock()

    fact_obj = MagicMock()
    fact_obj.id = 55
    fact_obj.statement = "RBI repo rate is 5.5%"
    fact_obj.subject = "repo rate"
    fact_obj.value = "5.5%"
    fact_obj.status = "verified"
    fact_obj.section = "economy"

    fact_result = MagicMock()
    fact_result.scalars.return_value.all.return_value = [fact_obj]

    chap_result = MagicMock()
    chap_result.scalars.return_value.all.return_value = []

    mock_session.execute.side_effect = [fact_result, chap_result]

    fc = FakeCompleter([SAMPLE_DRAFT.model_dump_json(), '{"answer_index": 0}'])
    result = await run_make_mcqs(mock_session, fc, now=now, limit=10)

    assert result.fact_mcqs_created == 1
    assert result.chapter_mcqs_created == 0
    assert result.total_created == 1
    assert mock_session.add.called
    assert mock_session.flush.called


def test_render_review_markdown():
    mcq = MCQ(
        id=1,
        fact_id=10,
        chunk_id=None,
        chapter_id=None,
        question="What is the capital of India?",
        options=["Mumbai", "New Delhi", "Kolkata", "Chennai"],
        answer_index=1,
        explanation="New Delhi is the official capital.",
        status="active",
        created_at=datetime(2026, 11, 15, 5, 30, tzinfo=UTC),
    )
    md = render_review_markdown([mcq], datetime(2026, 11, 15, tzinfo=UTC).date())
    assert "# MCQ Review Checklist - 2026-11-15" in md
    assert "## 1. MCQ #1 (Fact #10)" in md
    assert "**Question:** What is the capital of India?" in md
    assert "- [ ] **B.** New Delhi (Key)" in md


@pytest.mark.db
async def test_run_make_mcqs_skips_superseded_facts(session):
    from techradar.db.models import Fact

    new = Fact(
        fact_key="k-new",
        statement="Repo rate is 5.25%.",
        subject="repo rate",
        value="5.25%",
        section="economy",
        status="verified",
    )
    session.add(new)
    await session.flush()
    old = Fact(
        fact_key="k-old",
        statement="Repo rate is 5.5%.",
        subject="repo rate",
        value="5.5%",
        section="economy",
        status="verified",
        superseded_by=new.id,
    )
    session.add(old)
    await session.flush()
    draft = SAMPLE_DRAFT.model_copy(update={"options": ["5.25%", "5.0%", "6.0%", "6.5%"]})
    fc = FakeCompleter([draft.model_dump_json(), '{"answer_index": 0}'])
    result = await run_make_mcqs(session, fc, now=datetime(2026, 11, 15, tzinfo=UTC))
    assert result.fact_mcqs_created == 1 and len(fc.calls) == 2  # only the current fact
