from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from techradar.briefing.capsule import compose_capsule, month_start, run_capsule


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


def test_fact_with_no_date_is_not_in_any_capsule():
    f = SimpleNamespace(statement="Undated.", section="tech", status="verified", as_of=None)
    assert "Undated" not in compose_capsule(date(2026, 11, 1), [f])


def test_capsule_escapes_markdown_in_facts():
    f = SimpleNamespace(
        statement="GDP [grew](x) 7%", section="economy", status="verified", as_of=date(2026, 11, 2)
    )
    assert "[grew](x)" not in compose_capsule(date(2026, 11, 1), [f])


def test_month_start_is_the_previous_month():
    assert month_start(date(2026, 12, 1)) == date(2026, 11, 1)
    assert month_start(date(2027, 1, 1)) == date(2026, 12, 1)


async def test_run_capsule_writes_the_note_and_tells_the_owner(tmp_path, monkeypatch):
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    from techradar.briefing import capsule

    fact = SimpleNamespace(
        statement="Repo rate 5.25%.", section="economy", status="verified", as_of=date(2026, 11, 3)
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [fact]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    send = AsyncMock()
    monkeypatch.setattr(capsule, "enqueue_message", send)
    await run_capsule(
        session,
        tmp_path,
        date(2026, 11, 1),
        owner_chat_id=42,
        now=datetime(2026, 12, 1, tzinfo=UTC),
    )
    assert "Repo rate 5.25%." in (tmp_path / "capsules/2026-11.md").read_text(encoding="utf-8")
    assert send.await_args.kwargs["chat_id"] == 42
    assert (
        send.await_args.kwargs["text"]
        == "Your November capsule is in the vault: capsules/2026-11.md"
    )
