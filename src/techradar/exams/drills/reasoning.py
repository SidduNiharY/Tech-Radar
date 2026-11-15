from __future__ import annotations

import random
from typing import Any

from techradar.exams.drills.quant import DrillItem


def _make_item(
    kind: str,
    question: str,
    correct_option: str,
    distractors: list[str],
    explanation: str,
    meta: dict[str, Any],
    rng: random.Random,
) -> DrillItem:
    opts: list[str] = [correct_option]
    for d in distractors:
        if d not in opts:
            opts.append(d)
        if len(opts) == 4:
            break

    # Fill if needed
    counter = 1
    while len(opts) < 4:
        cand = f"Option {counter}"
        if cand not in opts:
            opts.append(cand)
        counter += 1

    rng.shuffle(opts)
    ans_idx = opts.index(correct_option)

    meta_clean: dict[str, int | float | str] = {}
    for k, v in meta.items():
        if isinstance(v, (int, float, str)):
            meta_clean[k] = v
        else:
            meta_clean[k] = str(v)

    return DrillItem(
        kind=kind,
        question=question,
        options=opts,
        answer_index=ans_idx,
        explanation=explanation,
        meta=meta_clean,
    )


def gen_number_series(rng: random.Random) -> DrillItem:
    kind = rng.choice(["arithmetic", "squares", "geometric", "cubes"])
    if kind == "arithmetic":
        start = rng.randint(2, 20)
        step = rng.randint(3, 12)
        seq = [start + i * step for i in range(4)]
        ans = start + 4 * step
        q = f"Find the next number in the series: {', '.join(map(str, seq))}, ?"
        distractors = [str(ans + step), str(ans - step), str(ans + 2)]
        meta = {"kind": kind, "start": start, "step": step, "ans": ans}
        expl = f"Common difference is {step}. Next term = {seq[-1]} + {step} = {ans}"
    elif kind == "squares":
        start = rng.randint(2, 10)
        seq = [(start + i) ** 2 for i in range(4)]
        ans = (start + 4) ** 2
        q = f"Find the next number in the series: {', '.join(map(str, seq))}, ?"
        distractors = [str(ans + 10), str(ans - 10), str((start + 5) ** 2)]
        meta = {"kind": kind, "start": start, "ans": ans}
        expl = f"Terms are squares of consecutive integers. Next term = {start + 4}² = {ans}"
    elif kind == "geometric":
        start = rng.randint(2, 5)
        ratio = rng.choice([2, 3])
        seq = [start * (ratio**i) for i in range(4)]
        ans = start * (ratio**4)
        q = f"Find the next number in the series: {', '.join(map(str, seq))}, ?"
        distractors = [str(ans + ratio), str(ans - ratio), str(ans * 2)]
        meta = {"kind": kind, "start": start, "ratio": ratio, "ans": ans}
        expl = f"Common ratio is {ratio}. Next term = {seq[-1]} × {ratio} = {ans}"
    else:  # cubes
        start = rng.randint(1, 5)
        seq = [(start + i) ** 3 for i in range(4)]
        ans = (start + 4) ** 3
        q = f"Find the next number in the series: {', '.join(map(str, seq))}, ?"
        distractors = [str(ans + 20), str(ans - 20), str((start + 4) ** 2)]
        meta = {"kind": kind, "start": start, "ans": ans}
        expl = f"Terms are cubes of consecutive numbers. Next term = {start + 4}³ = {ans}"

    return _make_item("reasoning_number_series", q, str(ans), distractors, expl, meta, rng)


def gen_coding_decoding(rng: random.Random) -> DrillItem:
    words = [
        "APPLE",
        "BRAIN",
        "CLOUD",
        "DREAM",
        "EARTH",
        "FLAME",
        "GIANT",
        "LIGHT",
        "NIGHT",
        "POWER",
    ]
    word = rng.choice(words)
    shift = rng.choice([1, 2, -1])

    def shift_word(w: str, s: int) -> str:
        return "".join(chr((ord(c) - 65 + s) % 26 + 65) for c in w)

    coded = shift_word(word, shift)
    q = (
        f"In a certain code language, '{word}' is written as '{coded}'. "
        "How is 'RIVER' coded using the same pattern?"
    )
    ans = shift_word("RIVER", shift)
    distractors = [
        shift_word("RIVER", shift + 1),
        shift_word("RIVER", shift - 1 if shift > 0 else shift - 2),
        shift_word("RIVER", -shift),
    ]
    meta = {"word": word, "coded": coded, "shift": shift, "ans": ans}
    expl = f"Each letter is shifted by {shift:+d} in the alphabet."
    return _make_item("reasoning_coding_decoding", q, ans, distractors, expl, meta, rng)


def gen_direction_sense(rng: random.Random) -> DrillItem:
    triples = [(3, 4, 5), (6, 8, 10), (5, 12, 13), (9, 12, 15), (8, 15, 17)]
    x, y, d = rng.choice(triples)
    q = (
        f"A person walks {x} km North from point A, then turns East and walks {y} km to point B. "
        f"What is the shortest distance between A and B?"
    )
    ans = f"{d} km"
    distractors = [f"{x + y} km", f"{d + 2} km", f"{max(1, d - 2)} km"]
    meta = {"x": x, "y": y, "ans": d}
    expl = f"Using Pythagorean theorem: d = √({x}² + {y}²) = √({x * x + y * y}) = {d} km"
    return _make_item("reasoning_direction_sense", q, ans, distractors, expl, meta, rng)


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


def gen_odd_one_out(rng: random.Random) -> DrillItem:
    # 3 primes + 1 composite
    primes = [11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]
    composites = [15, 21, 25, 27, 33, 35, 39, 45, 49]
    chosen_primes = rng.sample(primes, 3)
    composite = rng.choice(composites)

    q = "Find the odd one out from the given options."
    distractors = [str(p) for p in chosen_primes]
    meta = {"primes": ",".join(map(str, chosen_primes)), "composite": composite, "ans": composite}
    expl = (
        f"{composite} is a composite number ({composite} is divisible by other factors), "
        "whereas the others are prime numbers."
    )
    return _make_item("reasoning_odd_one_out", q, str(composite), distractors, expl, meta, rng)
