from __future__ import annotations

import random
from datetime import date

import pytest

from techradar.exams.drills import (
    daily_set,
    gen_approximation,
    gen_average,
    gen_coding_decoding,
    gen_compound_interest,
    gen_cube,
    gen_direction_sense,
    gen_number_series,
    gen_odd_one_out,
    gen_percent_change,
    gen_percent_fraction,
    gen_percentage_of,
    gen_profit_loss_percent,
    gen_ratio_share,
    gen_simple_interest,
    gen_square,
    gen_table,
    gen_time_speed_distance,
    gen_work_together,
    score_typing,
    typing_passage,
)


def _recompute_ci(m: dict[str, int | float | str]) -> str:
    p = float(m["p"])
    r = float(m["r"])
    t = float(m["t"])
    ci = round(p * (1 + r / 100) ** t - p, 2)
    return str(int(ci)) if ci == int(ci) else f"{ci:.2f}"


GENERATORS_WITH_ORACLES = [
    (gen_compound_interest, _recompute_ci),
    (gen_percentage_of, lambda m: str((int(m["p"]) * int(m["x"])) // 100)),
    (gen_percent_change, lambda m: f"{int(m['ans'])}%"),
    (gen_ratio_share, lambda m: str(int(m["ans"]))),
    (gen_simple_interest, lambda m: str((int(m["p"]) * int(m["r"]) * int(m["t"])) // 100)),
    (gen_profit_loss_percent, lambda m: f"{int(m['ans'])}%"),
    (gen_average, lambda m: str(int(m["ans"]))),
    (gen_time_speed_distance, lambda m: f"{int(m['ans'])} km"),
    (
        gen_work_together,
        lambda m: (
            f"{int(float(m['ans']))} days"
            if float(m["ans"]) == int(float(m["ans"]))
            else f"{float(m['ans']):.2f} days"
        ),
    ),
    (gen_number_series, lambda m: str(m["ans"])),
    (gen_coding_decoding, lambda m: str(m["ans"])),
    (gen_direction_sense, lambda m: f"{m['ans']} km"),
    (gen_odd_one_out, lambda m: str(m["ans"])),
    (gen_table, lambda m: str(int(m["a"]) * int(m["b"]))),
    (gen_square, lambda m: str(int(m["n"]) * int(m["n"]))),
    (gen_cube, lambda m: str(int(m["n"]) ** 3)),
    (gen_percent_fraction, lambda m: str(m["ans"])),
    (gen_approximation, lambda m: str(m["ans"])),
]


@pytest.mark.parametrize("gen,recompute", GENERATORS_WITH_ORACLES)
def test_generator_answers_are_correct(gen, recompute):
    for seed in range(200):
        item = gen(random.Random(seed))  # noqa: S311
        assert len(set(item.options)) == 4, (
            f"Options not unique for {gen.__name__} seed {seed}: {item.options}"
        )
        expected = recompute(item.meta)
        assert item.options[item.answer_index] == expected, (
            f"{gen.__name__} mismatch at seed {seed}: "
            f"got {item.options[item.answer_index]} != {expected}"
        )


def test_daily_set_same_for_same_day():
    d1 = date(2026, 11, 8)
    d2 = date(2026, 11, 9)
    set1 = daily_set(d1)
    set2 = daily_set(d1)
    set3 = daily_set(d2)

    assert len(set1) == 20
    assert [i.question for i in set1] == [i.question for i in set2]
    assert [i.question for i in set1] != [i.question for i in set3]


def test_score_typing():
    s = score_typing("hello world", "helo world", 6.0)
    assert s.accuracy == pytest.approx(1 - 1 / 11, abs=1e-3)
    assert s.wpm == pytest.approx(20.0, abs=0.5)
    assert s.key_depressions == 10


def test_typing_passage():
    sentences = [
        "The quick brown fox jumps over the lazy dog.",
        "Pack my box with five dozen liquor jugs.",
    ]
    rng = random.Random(42)  # noqa: S311
    passage = typing_passage(sentences, rng, target_keys=200)
    assert len(passage) >= 200
    assert all(ord(c) < 128 for c in passage)
