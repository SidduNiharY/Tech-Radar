from pathlib import Path

import trafilatura

from techradar.intake.textcheck import check_injection, pattern_hits

FIX_DIR = Path(__file__).parent / "fixtures"


def test_article_about_injection_is_flagged():
    html = (FIX_DIR / "article_about_injection.html").read_text()
    text = trafilatura.extract(html) or ""
    hits = pattern_hits(text)
    assert "ignore_previous" in hits
    assert check_injection(0.9, hits).outcome == "flag"


def test_obvious_injection_quarantined():
    assert check_injection(0.99, ["ignore_previous", "you_are_now"]).outcome == "quarantine"


def test_injection_never_rejects():
    assert check_injection(1.0, ["a", "b", "c"]).outcome != "reject"


def test_clean_text_is_ok():
    assert check_injection(0.1, []).outcome == "ok"
