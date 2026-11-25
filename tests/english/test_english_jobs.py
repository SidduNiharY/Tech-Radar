from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from techradar.english import jobs
from techradar.english.grammar_check import GrammarIssue
from techradar.english.jobs import (
    LETTER_REF,
    is_timed,
    pick_topic,
    prompt_kind,
    read_topics,
    run_essay_prompt,
    run_essay_reply,
    run_polish,
    run_reading_quiz,
    run_reflection_prompt,
)
from tests.fakes import FakeCompleter


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, row: Any) -> None:
        self.added.append(row)


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    async def fake_enqueue(session: Any, chat_id: int, text: str, **kw: Any) -> int:
        out.append({"chat_id": chat_id, "text": text, **kw})
        return len(out)

    monkeypatch.setattr(jobs, "enqueue_message", fake_enqueue)
    return out


FEEDBACK = json.dumps({"improved": "Better text.", "reasons": ["Clearer."]})
RUBRIC_FEEDBACK = json.dumps(
    {
        "improved": "Dear Sir, ...",
        "reasons": ["Concise."],
        "rubric": {"structure": 4, "grammar": 3, "vocabulary": 4, "relevance": 5},
    }
)


class DownLT:
    async def check(self, text: str) -> list[GrammarIssue]:
        raise ConnectionError("languagetool is down")


async def test_polish_sends_feedback_and_stores_it(sent: list[dict[str, Any]]) -> None:
    session = FakeSession()
    reply = await run_polish(
        session,  # type: ignore[arg-type]
        "me go home",
        owner_chat_id=42,
        lt=None,
        completer=FakeCompleter([FEEDBACK]),
    )
    assert reply.startswith("Improved:\nBetter text.")
    assert sent[0]["chat_id"] == 42 and sent[0]["purpose"] == "polish"
    assert session.added[0].source_kind == "polish"


async def test_polish_refuses_long_and_empty_text(sent: list[dict[str, Any]]) -> None:
    session = FakeSession()
    long_reply = await run_polish(
        session,  # type: ignore[arg-type]
        "x" * 2001,
        owner_chat_id=42,
        lt=None,
        completer=FakeCompleter([]),
    )
    empty_reply = await run_polish(
        session,  # type: ignore[arg-type]
        "  ",
        owner_chat_id=42,
        lt=None,
        completer=FakeCompleter([]),
    )
    assert long_reply == "Keep it under 2,000 characters."
    assert empty_reply == "Send /polish followed by your text."
    assert session.added == []


async def test_polish_survives_languagetool_down_and_model_failure(
    sent: list[dict[str, Any]],
) -> None:
    session = FakeSession()
    ok = await run_polish(
        session,  # type: ignore[arg-type]
        "hello",
        owner_chat_id=42,
        lt=DownLT(),
        completer=FakeCompleter([FEEDBACK]),
    )
    assert ok.startswith("Improved:")
    failed = await run_polish(
        session,  # type: ignore[arg-type]
        "hello",
        owner_chat_id=42,
        lt=None,
        completer=FakeCompleter([]),
    )
    assert failed == jobs.FEEDBACK_FAILED


def test_essays_and_letters_alternate_and_topics_are_stable(tmp_path: Path) -> None:
    mon, next_mon = date(2026, 11, 23), date(2026, 11, 30)
    assert prompt_kind(mon) != prompt_kind(next_mon)
    topics = ["a", "b", "c"]
    assert pick_topic(topics, mon) == pick_topic(topics, date(2026, 11, 28))
    (tmp_path / "practice").mkdir()
    (tmp_path / "practice" / "essay_topics.md").write_text("# Topics\n- Water\n* Roads\n")
    assert read_topics(tmp_path) == ["Water", "Roads"]
    assert read_topics(tmp_path / "nowhere") == list(jobs.DEFAULT_TOPICS)


async def test_essay_prompt_uses_purpose_essay(sent: list[dict[str, Any]], tmp_path: Path) -> None:
    kind = await run_essay_prompt(
        FakeSession(),  # type: ignore[arg-type]
        date(2026, 11, 28),
        owner_chat_id=42,
        vault_root=tmp_path,
    )
    assert sent[0]["purpose"] == "essay"
    assert sent[0]["ref_id"] == (LETTER_REF if kind == "letter" else 1)
    assert "30 minutes" in sent[0]["text"]


async def test_essay_reply_has_rubric_and_marks_untimed(sent: list[dict[str, Any]]) -> None:
    session = FakeSession()
    reply = await run_essay_reply(
        session,  # type: ignore[arg-type]
        "Dear Sir, I write.",
        ref_id=LETTER_REF,
        timed=False,
        owner_chat_id=42,
        lt=None,
        completer=FakeCompleter([RUBRIC_FEEDBACK]),
    )
    assert "Structure 4 · Grammar 3" in reply and reply.endswith("(untimed)")
    assert session.added[0].source_kind == "letter"


def test_timed_window() -> None:
    t = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    assert is_timed(t, t + timedelta(minutes=30))
    assert not is_timed(t, t + timedelta(minutes=31))


async def test_reflection_prompt(sent: list[dict[str, Any]]) -> None:
    await run_reflection_prompt(FakeSession(), owner_chat_id=42)  # type: ignore[arg-type]
    assert sent[0]["purpose"] == "reflection"
    assert sent[0]["text"].startswith("One conversation this week")


async def test_reading_quiz_sends_questions_then_answers(
    sent: list[dict[str, Any]], tmp_path: Path
) -> None:
    from tests.english.test_reading import MCQ_VERBATIM, NOTE

    news = tmp_path / "wiki" / "news" / "2026" / "11"
    news.mkdir(parents=True)
    (news / "moon.md").write_text(NOTE)
    n = await run_reading_quiz(
        FakeSession(),  # type: ignore[arg-type]
        date(2026, 11, 27),
        owner_chat_id=42,
        vault_root=tmp_path,
        completer=FakeCompleter([MCQ_VERBATIM, '{"answer_index": 0}']),
    )
    assert n == 1
    assert [m["purpose"] for m in sent] == ["reading_quiz", "reading_answers"]
    assert "A. Neil Armstrong" in sent[0]["text"] and sent[1]["text"].startswith("Answers\n1. A")


async def test_reading_quiz_without_notes_sends_nothing(
    sent: list[dict[str, Any]], tmp_path: Path
) -> None:
    n = await run_reading_quiz(
        FakeSession(),  # type: ignore[arg-type]
        date(2026, 11, 27),
        owner_chat_id=42,
        vault_root=tmp_path,
        completer=FakeCompleter([]),
    )
    assert n == 0 and sent == []
