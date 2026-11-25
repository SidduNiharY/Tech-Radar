"""A style profile changes the form of an answer, never the checks (Phase 11 Task 7).

SEC: SEC-17, SEC-38, SEC-48.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from techradar.feedback.patterns import Mode
from techradar.feedback.rules import StyleRule
from techradar.profile.style import INVARIANT_LINE, render_profile_block
from techradar.rag.answer import answer_question
from tests.fakes import FakeCompleter
from tests.rag.test_answer import HITS, make_deps

BLOCK = render_profile_block([StyleRule(mode=Mode.GATE, field="length", value="short")])
UNCITED = json.dumps({"answer": "The CRR is a reserve ratio.", "citations": []})
CITED = json.dumps({"answer": "The repo rate is 6.5% [C1].", "citations": ["C1"]})


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> None:
    async def mock_retrieve(*args: Any, **kwargs: Any) -> Any:
        return HITS

    monkeypatch.setattr("techradar.rag.answer.retrieve", mock_retrieve)


async def test_profile_never_relaxes_citations(patched) -> None:
    completer = FakeCompleter([UNCITED, UNCITED])
    a = await answer_question("What is CRR?", make_deps(HITS, completer), profile=BLOCK)
    assert a.status == "needs_review" and "bad_citation" in a.flags


async def test_profile_joins_the_system_prompt_only(patched) -> None:
    completer = FakeCompleter([CITED])
    a = await answer_question("What is the repo rate?", make_deps(HITS, completer), profile=BLOCK)
    assert a.status == "answered"
    system = completer.calls[0]["messages"][0]["content"]
    user = completer.calls[0]["messages"][1]["content"]
    assert "My preferences:" in system and "Keep the answer under 120 words." in system
    assert INVARIANT_LINE in system
    assert "My preferences" not in user  # the excerpts stay untouched


async def test_no_profile_leaves_the_prompt_as_before(patched) -> None:
    completer = FakeCompleter([CITED])
    await answer_question("What is the repo rate?", make_deps(HITS, completer))
    assert "My preferences" not in completer.calls[0]["messages"][0]["content"]
