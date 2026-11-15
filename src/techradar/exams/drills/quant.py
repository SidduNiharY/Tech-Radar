from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel


class DrillItem(BaseModel):
    kind: str
    question: str
    options: list[str]  # exactly 4, unique
    answer_index: int
    explanation: str
    meta: dict[str, int | float | str]


def _build_item(
    kind: str,
    question: str,
    ans_val: int | float,
    distractors: list[int | float],
    explanation: str,
    meta: dict[str, Any],
    rng: random.Random,
    format_fn: Any = None,
) -> DrillItem:
    if format_fn is None:

        def fmt(x: int | float) -> str:
            if isinstance(x, int) or x == int(x):
                return str(int(x))
            return f"{x:.2f}"
    else:
        fmt = format_fn

    correct_str = fmt(ans_val)
    opts_set: set[str] = {correct_str}

    # Add candidate distractors
    for d in distractors:
        ds = fmt(d)
        if ds not in opts_set:
            opts_set.add(ds)
        if len(opts_set) == 4:
            break

    # If fewer than 4 unique, generate random variations
    offset = 1
    while len(opts_set) < 4:
        cand = ans_val + offset
        cs = fmt(cand)
        if cs not in opts_set:
            opts_set.add(cs)
        offset = -offset if offset > 0 else (-offset + 1)

    options = list(opts_set)
    rng.shuffle(options)
    ans_idx = options.index(correct_str)

    meta_clean: dict[str, int | float | str] = {}
    for k, v in meta.items():
        if isinstance(v, (int, float, str)):
            meta_clean[k] = v
        else:
            meta_clean[k] = str(v)

    return DrillItem(
        kind=kind,
        question=question,
        options=options,
        answer_index=ans_idx,
        explanation=explanation,
        meta=meta_clean,
    )


def gen_percentage_of(rng: random.Random) -> DrillItem:
    p = rng.choice([5, 10, 15, 20, 25, 30, 40, 50, 60, 75])
    x = rng.choice([20, 40, 60, 80, 100, 120, 150, 200, 250, 300, 400, 500])
    ans = (p * x) // 100
    q = f"What is {p}% of {x}?"
    distractors = [ans + 5, max(1, ans - 5), (p * x) // 10, ans + 10]
    return _build_item(
        "quant_percentage_of",
        q,
        ans,
        distractors,
        f"{p}% of {x} = ({p} × {x}) / 100 = {ans}",
        {"p": p, "x": x, "ans": ans},
        rng,
    )


def gen_percent_change(rng: random.Random) -> DrillItem:
    old = rng.choice([50, 80, 100, 120, 150, 200, 250])
    pct = rng.choice([-30, -25, -20, -10, 10, 20, 25, 30, 50])
    new = old + (old * pct) // 100
    q = f"What is the percentage change from {old} to {new}?"
    distractors = [pct + 5, pct - 5, -pct, pct + 10]
    return _build_item(
        "quant_percent_change",
        q,
        pct,
        distractors,
        f"Change = ({new} - {old}) / {old} × 100% = {pct}%",
        {"old": old, "new": new, "ans": pct},
        rng,
        format_fn=lambda v: f"{int(v)}%" if v == int(v) else f"{v:.1f}%",
    )


def gen_ratio_share(rng: random.Random) -> DrillItem:
    a = rng.randint(2, 7)
    b = rng.randint(2, 7)
    while b == a:
        b = rng.randint(2, 7)
    m = rng.choice([10, 20, 25, 50, 100])
    total = (a + b) * m
    ans = max(a, b) * m
    q = f"Divide Rs. {total} in the ratio {a}:{b}. What is the larger share?"
    distractors = [min(a, b) * m, ans + m, max(m, ans - m)]
    return _build_item(
        "quant_ratio_share",
        q,
        ans,
        distractors,
        f"Larger share = {max(a, b)} / ({a} + {b}) × {total} = {ans}",
        {"a": a, "b": b, "total": total, "ans": ans},
        rng,
    )


def gen_simple_interest(rng: random.Random) -> DrillItem:
    p = rng.choice([1000, 2000, 5000, 10000])
    r = rng.choice([5, 6, 8, 10, 12])
    t = rng.choice([2, 3, 4, 5])
    si = (p * r * t) // 100
    q = f"Calculate the simple interest on Rs. {p} at {r}% per annum for {t} years."
    distractors = [si + 100, max(50, si - 100), (p * r) // 100, si + 200]
    return _build_item(
        "quant_simple_interest",
        q,
        si,
        distractors,
        f"SI = (P × R × T) / 100 = ({p} × {r} × {t}) / 100 = {si}",
        {"p": p, "r": r, "t": t, "ans": si},
        rng,
    )


def gen_compound_interest(rng: random.Random) -> DrillItem:
    p = rng.choice([1000, 2000, 5000, 10000])
    r = rng.choice([5, 10, 20])
    t = rng.choice([2, 3])
    ci = round(p * ((1 + r / 100) ** t) - p, 2)
    si = (p * r * t) // 100
    q = f"Find the compound interest on Rs. {p} compounded annually at {r}% for {t} years."
    distractors = [si, round(ci + 50, 2), round(max(10.0, ci - 50), 2), round(ci * 1.1, 2)]
    return _build_item(
        "quant_compound_interest",
        q,
        ci,
        distractors,
        f"CI = P(1 + r/100)^t - P = {p}(1 + {r / 100})^{t} - {p} = {ci}",
        {"p": p, "r": r, "t": t, "ans": ci},
        rng,
    )


def gen_profit_loss_percent(rng: random.Random) -> DrillItem:
    cp = rng.choice([50, 80, 100, 150, 200, 250, 400, 500])
    pct = rng.choice([10, 15, 20, 25, 30])
    sp = cp + (cp * pct) // 100
    q = f"An article bought for Rs. {cp} is sold for Rs. {sp}. Find the profit percentage."
    distractors = [pct + 5, pct - 5, pct + 10, pct - 2]
    return _build_item(
        "quant_profit_loss_percent",
        q,
        pct,
        distractors,
        f"Profit % = ({sp} - {cp}) / {cp} × 100% = {pct}%",
        {"cp": cp, "sp": sp, "ans": pct},
        rng,
        format_fn=lambda v: f"{int(v)}%" if v == int(v) else f"{v:.1f}%",
    )


def gen_average(rng: random.Random) -> DrillItem:
    count = rng.choice([4, 5])
    base = rng.randint(20, 60)
    diffs = [rng.randint(-15, 15) for _ in range(count - 1)]
    last_diff = -sum(diffs)
    diffs.append(last_diff)
    numbers = [base + d for d in diffs]
    avg = sum(numbers) // count
    nums_str = ", ".join(map(str, numbers))
    q = f"Find the average of the following numbers: {nums_str}."
    distractors = [avg + 2, avg - 2, avg + 4, avg - 4]
    return _build_item(
        "quant_average",
        q,
        avg,
        distractors,
        f"Average = ({nums_str.replace(', ', ' + ')}) / {count} = {avg}",
        {"numbers": ",".join(map(str, numbers)), "ans": avg},
        rng,
    )


def gen_time_speed_distance(rng: random.Random) -> DrillItem:
    speed = rng.choice([30, 40, 50, 60, 75, 80, 90, 100])
    t = rng.choice([2, 3, 4, 5])
    dist = speed * t
    q = f"A car travels at a constant speed of {speed} km/h for {t} hours. How far does it travel?"
    distractors = [dist + 20, dist - 20, speed + t, dist + 40]
    return _build_item(
        "quant_time_speed_distance",
        q,
        dist,
        distractors,
        f"Distance = Speed × Time = {speed} × {t} = {dist} km",
        {"speed": speed, "time": t, "ans": dist},
        rng,
        format_fn=lambda v: f"{int(v)} km",
    )


def gen_work_together(rng: random.Random) -> DrillItem:
    pairs = [(10, 15), (12, 24), (20, 30), (12, 18), (6, 12), (15, 30)]
    a, b = rng.choice(pairs)
    ans = round((a * b) / (a + b), 2)
    q = (
        f"A can complete a piece of work in {a} days and B in {b} days. "
        "How many days will they take together?"
    )
    distractors = [round(ans + 1, 2), round(max(1.0, ans - 1), 2), round((a + b) / 2, 2)]
    return _build_item(
        "quant_work_together",
        q,
        ans,
        distractors,
        f"Time = (A × B) / (A + B) = ({a} × {b}) / ({a} + {b}) = {ans} days",
        {"a": a, "b": b, "ans": ans},
        rng,
        format_fn=lambda v: f"{int(v)} days" if v == int(v) else f"{v:.2f} days",
    )
