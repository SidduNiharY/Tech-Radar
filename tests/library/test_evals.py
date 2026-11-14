"""Picking chunks for the book evals (Phase 2c Task 7); no database."""

from __future__ import annotations

from techradar.library.evals import pick_across_chapters, pick_spread


def test_pick_spread_is_even_ordered_and_distinct():
    assert pick_spread(list(range(10)), 5) == [1, 3, 5, 7, 9]
    assert pick_spread(list(range(3)), 5) == [0, 1, 2]
    assert pick_spread(list(range(3)), 0) == []
    for n in range(1, 40):
        for k in range(1, n):
            got = pick_spread(list(range(n)), k)
            assert len(got) == len(set(got)) == k and got == sorted(got)


def test_every_chapter_gets_a_share():
    groups = [[f"c{c}.{i}" for i in range(4)] for c in range(3)]
    got = pick_across_chapters(groups, 6)
    assert len(got) == 6
    assert {x.split(".")[0] for x in got} == {"c0", "c1", "c2"}


def test_small_chapters_give_their_spare_picks_to_big_ones():
    groups = [["a"], ["b1", "b2", "b3", "b4", "b5"], ["c"]]
    got = pick_across_chapters(groups, 5)
    assert len(got) == 5 and "a" in got and "c" in got


def test_fewer_picks_than_chapters_spreads_over_the_book():
    groups = [[f"c{c}"] for c in range(10)]
    assert pick_across_chapters(groups, 3) == ["c1", "c5", "c8"]


def test_asking_for_more_than_exists_returns_everything():
    assert pick_across_chapters([["a", "b"], ["c"]], 15) == ["a", "b", "c"]
    assert pick_across_chapters([], 5) == []
    assert pick_across_chapters([["a"]], 0) == []
