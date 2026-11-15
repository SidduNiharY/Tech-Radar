from __future__ import annotations

import httpx
import pytest
import respx

from techradar.english.grammar_check import check_grammar, top_rule
from techradar.practice.grammar import GrammarRule

BASE = "http://languagetool.tools:8010"

LT_FIXTURE = {
    "software": {"name": "LanguageTool", "version": "6.0"},
    "matches": [
        {
            "message": "Use 'a' instead of 'an' before consonant sounds.",
            "offset": 6,
            "length": 2,
            "replacements": [{"value": "a"}],
            "rule": {
                "id": "EN_A_VS_AN",
                "category": {"name": "Miscellaneous"},
            },
        },
        {
            "message": "Subject-verb agreement error.",
            "offset": 0,
            "length": 5,
            "replacements": [{"value": "He has"}],
            "rule": {
                "id": "HE_VERB_AGR",
                "category": {"name": "Grammar"},
            },
        },
    ],
}


@pytest.mark.asyncio
async def test_check_grammar_parses_fixture():
    async with respx.mock:
        respx.post(f"{BASE}/v2/check").respond(json=LT_FIXTURE)
        async with httpx.AsyncClient() as client:
            issues = await check_grammar(client, BASE, "I has a apple")
            assert {i.rule for i in issues} == {
                GrammarRule.ARTICLES,
                GrammarRule.SUBJECT_VERB,
            }
            assert issues[0].message.startswith("Use 'a' instead")
            assert issues[0].replacements == ["a"]


@pytest.mark.asyncio
async def test_text_capped():
    async with respx.mock:
        route = respx.post(f"{BASE}/v2/check").respond(json={"matches": []})
        async with httpx.AsyncClient() as client:
            long_text = "a" * 6000
            await check_grammar(client, BASE, long_text)
            assert route.called
            sent_text = route.calls.last.request.read().decode("utf-8")
            # Should contain at most 5000 'a's
            assert "a" * 5000 in sent_text
            assert "a" * 5001 not in sent_text


@pytest.mark.asyncio
async def test_top_rule():
    async with respx.mock:
        respx.post(f"{BASE}/v2/check").respond(json=LT_FIXTURE)
        async with httpx.AsyncClient() as client:
            issues = await check_grammar(client, BASE, "Sample text")
            best = top_rule(issues)
            assert best in (GrammarRule.ARTICLES, GrammarRule.SUBJECT_VERB)
            assert top_rule([]) is None
