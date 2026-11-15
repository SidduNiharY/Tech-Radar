from __future__ import annotations

from datetime import date

from techradar.night.timelines import timeline_entries


class FakeCluster:
    def __init__(self, date_val: date, title: str, entities: list[str], note_path: str) -> None:
        self.date = date_val
        self.title = title
        self.entities = entities
        self.note_path = note_path


def test_timeline_sorted_by_date() -> None:
    c1 = FakeCluster(date(2026, 11, 5), "RBI MPC Meeting", ["RBI", "Govt"], "notes/rbi1.md")
    c2 = FakeCluster(date(2026, 10, 1), "RBI Repo Hike", ["rbi"], "notes/rbi0.md")
    c3 = FakeCluster(date(2026, 11, 2), "Tech Stocks Fall", ["NASDAQ"], "notes/tech.md")

    entries = timeline_entries([c1, c2, c3], "RBI")
    assert len(entries) == 2
    assert entries[0].date == date(2026, 10, 1)
    assert entries[1].date == date(2026, 11, 5)
    assert entries[0].title == "RBI Repo Hike"
