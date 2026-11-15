from __future__ import annotations

import random

from techradar.exams.drills.quant import DrillItem, _build_item


def gen_table(rng: random.Random) -> DrillItem:
    a = rng.randint(2, 30)
    b = rng.randint(2, 12)
    ans = a * b
    q = f"Calculate: {a} × {b} = ?"
    distractors = [ans + a, max(1, ans - a), ans + b, ans + 10]
    return _build_item(
        "speed_table",
        q,
        ans,
        distractors,
        f"{a} × {b} = {ans}",
        {"a": a, "b": b, "ans": ans},
        rng,
    )


def gen_square(rng: random.Random) -> DrillItem:
    n = rng.randint(1, 50)
    ans = n * n
    q = f"Calculate the square of {n} ({n}²):"
    distractors = [ans + 2 * n, max(1, ans - 2 * n), (n + 1) ** 2, (n - 1) ** 2 if n > 1 else 4]
    return _build_item(
        "speed_square",
        q,
        ans,
        distractors,
        f"{n}² = {n} × {n} = {ans}",
        {"n": n, "ans": ans},
        rng,
    )


def gen_cube(rng: random.Random) -> DrillItem:
    n = rng.randint(1, 20)
    ans = n * n * n
    q = f"Calculate the cube of {n} ({n}³):"
    distractors = [ans + n * n, max(1, ans - n * n), (n + 1) ** 3, (n - 1) ** 3 if n > 1 else 8]
    return _build_item(
        "speed_cube",
        q,
        ans,
        distractors,
        f"{n}³ = {n} × {n} × {n} = {ans}",
        {"n": n, "ans": ans},
        rng,
    )


def gen_percent_fraction(rng: random.Random) -> DrillItem:
    fractions = [
        (1, 2, "50%"),
        (1, 3, "33.33%"),
        (1, 4, "25%"),
        (1, 5, "20%"),
        (1, 6, "16.67%"),
        (1, 8, "12.5%"),
        (1, 10, "10%"),
        (1, 12, "8.33%"),
        (3, 4, "75%"),
        (2, 5, "40%"),
        (3, 8, "37.5%"),
    ]
    num, den, pct = rng.choice(fractions)
    q = f"Convert the fraction {num}/{den} to its percentage equivalent:"
    other_pcts = [p for _, _, p in fractions if p != pct]
    distractors = rng.sample(other_pcts, 3)

    opts = [pct] + distractors
    rng.shuffle(opts)
    ans_idx = opts.index(pct)

    return DrillItem(
        kind="speed_percent_fraction",
        question=q,
        options=opts,
        answer_index=ans_idx,
        explanation=f"{num}/{den} = ({num} / {den}) × 100% = {pct}",
        meta={"num": num, "den": den, "ans": pct},
    )


def gen_approximation(rng: random.Random) -> DrillItem:
    # Two 2-digit numbers, options spaced at least 10% apart
    a = rng.randint(21, 89)
    b = rng.randint(15, 65)
    exact = a * b
    # Round to 2 significant digits / nearest ten/hundred
    base = round(exact / 10) * 10

    # Distractors spaced by at least 15%
    d1 = round(base * 0.75 / 10) * 10
    d2 = round(base * 1.25 / 10) * 10
    d3 = round(base * 1.50 / 10) * 10

    opts = [f"~{base}", f"~{d1}", f"~{d2}", f"~{d3}"]
    rng.shuffle(opts)
    ans_idx = opts.index(f"~{base}")

    return DrillItem(
        kind="speed_approximation",
        question=f"Approximate the product: {a} × {b} ≈ ?",
        options=opts,
        answer_index=ans_idx,
        explanation=f"{a} × {b} = {exact} ≈ {base}",
        meta={"a": a, "b": b, "exact": exact, "ans": f"~{base}"},
    )
