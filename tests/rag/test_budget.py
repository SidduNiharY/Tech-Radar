"""Conservative token counts and prompt budgets for the 8,192-token model context (SEC-41)."""

import pytest

from techradar.rag.budget import (
    NUM_CTX,
    conservative_tokens,
    context_budget,
    cut_to_tokens,
    fit_texts,
    prompt_fits,
)

INDIC = "भारतीय रिज़र्व बैंक ने रेपो दर को स्थिर रखा। " * 50


def test_num_ctx_matches_every_role() -> None:
    assert NUM_CTX == 8192


def test_conservative_tokens_never_undercounts_like_word_counts() -> None:
    blob = "x" * 10_000  # an OCR blob or minified code: one "word"
    assert conservative_tokens(blob) >= 10_000 // 3
    words = "word " * 100
    assert conservative_tokens(words) >= 130
    assert conservative_tokens("") == 0


def test_non_latin_text_counts_at_least_one_token_per_character() -> None:
    non_ascii = sum(1 for c in INDIC if ord(c) > 127)
    assert conservative_tokens(INDIC) >= non_ascii


def test_context_budget() -> None:
    assert context_budget(max_tokens=1000, system_tokens=200, margin=100) == NUM_CTX - 1300
    assert context_budget(max_tokens=9000, system_tokens=0, margin=0) == 0


def test_prompt_fits() -> None:
    assert prompt_fits("sys", "user", max_tokens=1000)
    assert not prompt_fits("sys", "x" * 30_000, max_tokens=1000)


@pytest.mark.parametrize("text", ["x" * 10_000, INDIC, "word " * 4000])
def test_cut_to_tokens_fits_and_is_a_prefix(text: str) -> None:
    cut = cut_to_tokens(text, 500)
    assert conservative_tokens(cut) <= 500
    assert text.startswith(cut)
    assert len(cut) > 0


def test_cut_to_tokens_prefers_a_word_boundary_and_keeps_short_text() -> None:
    assert cut_to_tokens("short text", 500) == "short text"
    cut = cut_to_tokens("alpha beta gamma delta " * 200, 100)
    assert cut.endswith(("alpha", "beta", "gamma", "delta"))
    assert cut_to_tokens("anything", 0) == ""


def test_fit_texts_keeps_every_text_and_shares_the_budget() -> None:
    texts = ["short one", "y" * 9000, "z" * 9000, "tiny"]
    out = fit_texts(texts, 2000)
    assert len(out) == 4
    assert out[0] == "short one" and out[3] == "tiny"  # small texts are never cut
    assert sum(conservative_tokens(t) for t in out) <= 2000
    assert all(t for t in out)
    for orig, got in zip(texts, out, strict=True):
        assert orig.startswith(got)


def test_fit_texts_unchanged_when_everything_fits() -> None:
    assert fit_texts(["a b", "c d"], 1000) == ["a b", "c d"]
