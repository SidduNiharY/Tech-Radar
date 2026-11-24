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


def _num(v: float) -> str:
    return f"{round(v, 2):g}"


def _recompute_ci(m: dict[str, int | float | str]) -> str:
    p, r, t = float(m["p"]), float(m["r"]), float(m["t"])
    ci = round(p * (1 + r / 100) ** t - p, 2)
    return str(int(ci)) if ci == int(ci) else f"{ci:.2f}"


def _shift(word: str, s: int) -> str:
    return "".join(chr((ord(c) - 65 + s) % 26 + 65) for c in word)


def _series_next(m: dict[str, int | float | str]) -> str:
    start = int(m["start"])
    nxt = {
        "arithmetic": lambda: start + 4 * int(m.get("step", 0)),
        "squares": lambda: (start + 4) ** 2,
        "geometric": lambda: start * int(m.get("ratio", 1)) ** 4,
        "cubes": lambda: (start + 4) ** 3,
    }[str(m["kind"])]()
    return str(nxt)


def _is_prime(n: int) -> bool:
    return n > 1 and all(n % i for i in range(2, int(n**0.5) + 1))


def _odd_one_out(m: dict[str, int | float | str]) -> str:
    primes = [int(x) for x in str(m["primes"]).split(",")]
    composite = int(m["composite"])
    assert all(_is_prime(p) for p in primes) and not _is_prime(composite)
    return str(composite)


# Each oracle recomputes the answer from the question's own inputs, never from `meta["ans"]`.
GENERATORS_WITH_ORACLES = [
    (gen_compound_interest, _recompute_ci),
    (gen_percentage_of, lambda m: _num(int(m["p"]) * int(m["x"]) / 100)),
    (
        gen_percent_change,
        lambda m: _num((int(m["new"]) - int(m["old"])) * 100 / int(m["old"])) + "%",
    ),
    (
        gen_ratio_share,
        lambda m: _num(
            int(m["total"]) * max(int(m["a"]), int(m["b"])) / (int(m["a"]) + int(m["b"]))
        ),
    ),
    (gen_simple_interest, lambda m: _num(int(m["p"]) * int(m["r"]) * int(m["t"]) / 100)),
    (
        gen_profit_loss_percent,
        lambda m: _num((int(m["sp"]) - int(m["cp"])) * 100 / int(m["cp"])) + "%",
    ),
    (
        gen_average,
        lambda m: _num(
            sum(map(int, str(m["numbers"]).split(","))) / len(str(m["numbers"]).split(","))
        ),
    ),
    (gen_time_speed_distance, lambda m: f"{int(m['speed']) * int(m['time'])} km"),
    (
        gen_work_together,
        lambda m: (
            f"{int(m['a']) * int(m['b']) // (int(m['a']) + int(m['b']))} days"
            if int(m["a"]) * int(m["b"]) % (int(m["a"]) + int(m["b"])) == 0
            else f"{int(m['a']) * int(m['b']) / (int(m['a']) + int(m['b'])):.2f} days"
        ),
    ),
    (gen_number_series, _series_next),
    (gen_coding_decoding, lambda m: _shift("RIVER", int(m["shift"]))),
    (gen_direction_sense, lambda m: f"{round((int(m['x']) ** 2 + int(m['y']) ** 2) ** 0.5)} km"),
    (gen_odd_one_out, _odd_one_out),
    (gen_table, lambda m: str(int(m["a"]) * int(m["b"]))),
    (gen_square, lambda m: str(int(m["n"]) * int(m["n"]))),
    (gen_cube, lambda m: str(int(m["n"]) ** 3)),
    (gen_percent_fraction, lambda m: _num(int(m["num"]) * 100 / int(m["den"])) + "%"),
    (gen_approximation, lambda m: f"~{round(int(m['a']) * int(m['b']) / 10) * 10}"),
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
