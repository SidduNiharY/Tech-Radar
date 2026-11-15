from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from techradar.briefing.capsule import compose_capsule


def test_capsule_includes_only_verified_facts_of_month():
    month = date(2026, 11, 1)

    # Facts: 1 verified in Nov 2026, 1 unverified in Nov 2026, 1 verified in Oct 2026
    f1 = SimpleNamespace(
        statement="RBI maintained Repo Rate at 6.5%.",
        section="economy",
        status="verified",
        as_of=date(2026, 11, 5),
    )
    f2 = SimpleNamespace(
        statement="Unverified rumor about crypto regulation.",
        section="economy",
        status="unverified",
        as_of=date(2026, 11, 6),
    )
    f3 = SimpleNamespace(
        statement="Old verified fact from October.",
        section="economy",
        status="verified",
        as_of=date(2026, 10, 15),
    )

    content = compose_capsule(month, [f1, f2, f3])
    assert "RBI maintained Repo Rate at 6.5%." in content
    assert "Unverified rumor" not in content
    assert "Old verified fact" not in content


def test_capsule_has_generated_front_matter():
    month = date(2026, 11, 1)
    f = SimpleNamespace(
        statement="Python 3.14 released with free-threading improvements.",
        section="tech",
        status="verified",
        as_of=date(2026, 11, 2),
    )
    content = compose_capsule(month, [f])
    assert content.startswith("---")
    assert "kind: capsule" in content
    assert "generated: true" in content
    assert "month: 2026-11" in content


def test_capsule_groups_by_section_order():
    month = date(2026, 11, 1)
    f_econ = SimpleNamespace(
        statement="GST revenue crossed 1.87 lakh crore.",
        section="economy",
        status="verified",
        as_of=date(2026, 11, 1),
    )
    f_tech = SimpleNamespace(
        statement="New open weights LLM released.",
        section="tech",
        status="verified",
        as_of=date(2026, 11, 1),
    )
    content = compose_capsule(month, [f_econ, f_tech])
    tech_pos = content.find("## Tech")
    econ_pos = content.find("## Economy")
    assert tech_pos != -1
    assert econ_pos != -1
    # Tech comes before Economy in SECTION_ORDER
    assert tech_pos < econ_pos
