from __future__ import annotations

from datetime import date

from techradar.night.timelines import (
    ClusterRow,
    render_timeline,
    timeline_entities,
    timeline_entries,
    timeline_rel_path,
)


def row(n: int, d: date, entities: list[str], title: str = "Story") -> ClusterRow:
    return ClusterRow(
        cluster_id=n,
        date=d,
        title=f"{title} {n}",
        note_path=f"wiki/news/2026/11/s{n}.md",
        entities=entities,
    )


CLUSTERS = [
    row(1, date(2026, 11, 5), ["RBI"]),
    row(2, date(2026, 11, 1), ["rbi", "SEBI"]),
    row(3, date(2026, 11, 3), ["Rbi"]),
    row(4, date(2026, 11, 2), ["SEBI"]),
]


def test_timeline_sorted_by_date() -> None:
    entries = timeline_entries(CLUSTERS, "RBI")
    assert [e.date for e in entries] == [date(2026, 11, 1), date(2026, 11, 3), date(2026, 11, 5)]
    assert timeline_entries(CLUSTERS, "nobody") == []


def test_entities_need_enough_stories() -> None:
    assert timeline_entities(CLUSTERS) == ["RBI"]
    assert timeline_entities(CLUSTERS, min_stories=2) == ["RBI", "SEBI"]


def test_render_links_notes_and_cleans_titles() -> None:
    entries = timeline_entries([row(1, date(2026, 11, 5), ["RBI"], title="Evil]] [[x|y")], "RBI")
    text = render_timeline("RBI", entries)
    assert "- **2026-11-05**: [[wiki/news/2026/11/s1|Evil x y 1]]" in text
    assert text.count("[[") == 1 and "generated: true" in text


def test_bad_note_path_is_shown_unlinked() -> None:
    bad = ClusterRow(
        cluster_id=1, date=date(2026, 11, 5), title="T", note_path="../../etc/x", entities=["A"]
    )
    assert "[[" not in render_timeline("A", timeline_entries([bad], "A"))


def test_hindi_entity_has_a_distinct_page() -> None:
    assert timeline_rel_path("भारतीय रिज़र्व बैंक").startswith("timelines/note-")
    assert "# Timeline: भारतीय रिज़र्व बैंक" in render_timeline("भारतीय रिज़र्व बैंक", [])
