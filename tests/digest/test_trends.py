"""Tests for trending topic detection, momentum ranking, and trends digest formatting."""

from datetime import UTC, datetime, timedelta

from techradar.digest.trends import (
    TopicTrend,
    format_trends_digest,
    normalise_term,
    rank_emerging_topics,
    rising,
)


def test_rising_detects_spike() -> None:
    """Test standard rising spike detection from Phase 10 task specification."""
    res = rising({"rust": 40}, {"rust": [5] * 14})
    assert len(res) == 1
    assert res[0].term == "rust"
    assert res[0].today == 40
    assert res[0].baseline == 5.0
    assert res[0].ratio == 8.0


def test_steady_term_not_rising() -> None:
    """Test that steady, consistently frequent terms are not flagged as rising fast."""
    assert rising({"india": 60}, {"india": [55] * 14}) == []


def test_min_count() -> None:
    """Test that terms with fewer mentions than min_count are rejected."""
    assert rising({"zig": 4}, {"zig": [0] * 14}) == []


def test_normalise_term() -> None:
    """Test term cleaning, case-folding, and whitespace collapsing."""
    assert normalise_term("  #Rust-Lang!  ") == "rust-lang"
    assert normalise_term("  Distributed   Systems  ") == "distributed systems"
    assert normalise_term("...Ollama...") == "ollama"


def test_normalise_term_indian_script() -> None:
    """Test that Indian language scripts (Devanagari, Telugu) are preserved."""
    assert normalise_term("  भारत सरकार ") == "भारत सरकार"
    assert normalise_term(" !కంప్యూటర్! ") == "కంప్యూటర్"


def test_rank_emerging_topics_ranking() -> None:
    """Test that emerging topics with surging velocity and momentum rank highest."""
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)

    # 1. 'deepseek': 20 mentions today, only 2 total in previous 14 days (huge surge)
    deepseek_mentions = [now - timedelta(hours=i) for i in range(20)] + [
        now - timedelta(days=5),
        now - timedelta(days=10),
    ]

    # 2. 'python': 5 mentions today, 70 in previous 14 days (~5 per day, steady)
    python_mentions = [now - timedelta(hours=i * 4) for i in range(5)] + [
        now - timedelta(days=d) for d in range(2, 16) for _ in range(5)
    ]

    # 3. 'quantum': 1 mention today, 0 previously
    quantum_mentions = [now - timedelta(hours=2)]

    mentions = {
        "deepseek": deepseek_mentions,
        "python": python_mentions,
        "quantum": quantum_mentions,
    }

    ranked = rank_emerging_topics(mentions, now, recent_days=1, baseline_days=14)
    assert len(ranked) >= 2
    # 'deepseek' must be rank 1 due to high momentum surge
    assert ranked[0].topic == "deepseek"
    assert ranked[0].recent_count == 20
    assert ranked[0].momentum > ranked[1].momentum


def test_rank_emerging_topics_empty() -> None:
    """Test that empty mentions mapping yields empty ranking."""
    now = datetime.now(UTC)
    assert rank_emerging_topics({}, now) == []


def test_format_trends_digest_empty() -> None:
    """Test that empty trends list yields empty string."""
    assert format_trends_digest([]) == ""


def test_format_trends_digest_with_trends() -> None:
    """Test formatted digest output containing emojis and metrics."""
    trends = [
        TopicTrend(
            topic="deepseek",
            recent_count=25,
            baseline_count=5,
            velocity=25.0,
            momentum=175.0,
            ratio=7.0,
        ),
        TopicTrend(
            topic="quantization",
            recent_count=10,
            baseline_count=6,
            velocity=10.0,
            momentum=23.3,
            ratio=2.33,
        ),
    ]
    digest = format_trends_digest(trends)
    assert "🔥 Emerging topic trends:" in digest
    assert "• deepseek: 25 mentions recently (velocity: 25.0/day, momentum: 175.0x)" in digest
    assert "• quantization: 10 mentions recently (velocity: 10.0/day, momentum: 23.3x)" in digest
