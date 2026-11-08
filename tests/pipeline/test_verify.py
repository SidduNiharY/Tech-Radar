"""Unit tests for multi-domain verification and quote-checked facts."""

import pytest

from techradar.pipeline.verify import (
    CHECKER_SYSTEM,
    check_fact,
    fact_key,
    headline_ok,
    is_verified,
)
from techradar.schemas.pipeline import CleanDoc, FactClaim, Section
from tests.fakes import FakeCompleter

OFFICIAL = frozenset({"rbi.org.in"})

SENTENCE_IN_DOC = "The Reserve Bank of India kept the policy repo rate unchanged at 5.5 percent."
DOC = CleanDoc(
    url="https://rbi.org.in/press/1",
    title="Monetary Policy Statement",
    text=f"Meeting on Friday. {SENTENCE_IN_DOC} Growth remains strong.",
    lang="en",
    truncated=False,
)
CLAIM = FactClaim(
    statement="RBI kept the repo rate unchanged.",
    subject="repo rate",
    value="5.5%",
)


def test_two_domains_verified():
    assert is_verified({"a.com", "b.in"}, OFFICIAL)


def test_one_news_domain_not_verified():
    assert not is_verified({"a.com"}, OFFICIAL)


def test_single_official_verified():
    assert is_verified({"rbi.org.in"}, OFFICIAL)


def test_politics_headline_needs_three():
    assert not headline_ok({"a.com", "b.in"}, Section.POLITICS, OFFICIAL)
    assert headline_ok({"a.com", "b.in", "c.org"}, Section.POLITICS, OFFICIAL)


def test_fact_key_stable_across_case_and_spacing():
    a = FactClaim(statement="x", subject="Repo  Rate", value="5.5%")
    b = FactClaim(statement="y", subject="repo rate", value=" 5.5% ")
    assert fact_key(a) == fact_key(b)


@pytest.mark.asyncio
async def test_check_fact_quote_must_exist():
    fc = FakeCompleter(['{"supported": true, "quote": "RBI cut rates to 1%."}'])
    assert not (await check_fact(fc, CLAIM, DOC)).supported


@pytest.mark.asyncio
async def test_check_fact_real_quote_supported():
    fc = FakeCompleter(['{"supported": true, "quote": "' + SENTENCE_IN_DOC + '"}'])
    verdict = await check_fact(fc, CLAIM, DOC)
    assert verdict.supported


@pytest.mark.asyncio
async def test_check_fact_invalid_output_unsupported():
    assert not (await check_fact(FakeCompleter(["nope", "nope"]), CLAIM, DOC)).supported


def test_checker_system_prompt_exact():
    assert (
        CHECKER_SYSTEM.splitlines()[0]
        == "You check one claim against one article for a personal study app."
    )
