from __future__ import annotations

import hashlib
import random
import re
from typing import Self

from pydantic import BaseModel, model_validator

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns (SEC-20)."""
    return bool(_LINK_RE.search(text))


class AptitudeProblem(BaseModel):
    id: str
    category: str
    question_text: str
    options: list[str]
    correct_index: int
    solution_steps: str

    @model_validator(mode="after")
    def validate_problem_integrity(self) -> Self:
        """Enforces SEC-20 security and schema integrity rules."""
        if len(self.options) != 4:
            raise ValueError(f"Problem must have exactly 4 options, got {len(self.options)}")
        if len(set(self.options)) != 4:
            raise ValueError("All 4 options must be strictly unique")
        if not (0 <= self.correct_index <= 3):
            raise ValueError(f"correct_index must be within [0, 3], got {self.correct_index}")
        if _contains_link(self.question_text):
            raise ValueError("question_text contains forbidden external link (SEC-20)")
        if _contains_link(self.solution_steps):
            raise ValueError("solution_steps contains forbidden external link (SEC-20)")
        for opt in self.options:
            if _contains_link(opt):
                raise ValueError("option contains forbidden external link (SEC-20)")
        return self

    def is_valid(self) -> bool:
        """Returns True if the problem conforms to schema and security constraints."""
        try:
            self.validate_problem_integrity()
            return True
        except ValueError:
            return False


def _build_options(
    correct_val: str,
    candidate_distractors: list[str],
    rng: random.Random,
) -> tuple[list[str], int]:
    """Assembles exactly 4 unique options and returns (shuffled_options, correct_index)."""
    distractors: list[str] = []
    for cand in candidate_distractors:
        c = str(cand).strip()
        if c != correct_val and c not in distractors:
            distractors.append(c)

    # Fallback to guarantee exactly 3 distinct distractors
    counter = 1
    while len(distractors) < 3:
        if "%" in correct_val:
            prefix = correct_val.replace("%", "").strip()
            try:
                num = float(prefix)
                alt = f"{num + counter * 5:g}%"
            except ValueError:
                alt = f"{prefix}_{counter}%"
        elif " seconds" in correct_val:
            num = int(correct_val.replace(" seconds", "").strip())
            alt = f"{num + counter * 4} seconds"
        elif " km/h" in correct_val:
            num = int(correct_val.replace(" km/h", "").strip())
            alt = f"{num + counter * 18} km/h"
        elif " m" in correct_val:
            num = int(correct_val.replace(" m", "").strip())
            alt = f"{num + counter * 50} m"
        else:
            try:
                num = int(correct_val)
                alt = str(num + counter * 2)
            except ValueError:
                alt = f"{correct_val}_{counter}"

        if alt != correct_val and alt not in distractors:
            distractors.append(alt)
        counter += 1

    options = [correct_val] + distractors[:3]
    rng.shuffle(options)
    correct_idx = options.index(correct_val)
    return options, correct_idx


def _stable_problem_num(seed: int, kind: str) -> int:
    """A 4-digit number fixed by (seed, kind). hash() is not used: str hashing
    changes between processes, so the same seed gave a different id each run."""
    digest = hashlib.sha256(f"{seed}:{kind}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 9000 + 1000


def generate_percentage_drill(seed: int | None = None) -> AptitudeProblem:
    """Generates an algorithmic percentage drill with programmatic ground truth (SEC-20)."""
    rng = random.Random(seed)  # noqa: S311
    problem_num = rng.randint(1000, 9999) if seed is None else _stable_problem_num(seed, "pct")
    problem_id = f"drill_pct_{problem_num}"

    template_type = rng.choice([0, 1, 2, 3])

    if template_type == 0:
        dataset = [
            (25, "20%", ["25%", "16.67%", "22.5%"]),
            (50, "33.33%", ["50%", "25%", "40%"]),
            (20, "16.67%", ["20%", "25%", "12.5%"]),
            (100, "50%", ["100%", "75%", "25%"]),
            (60, "37.5%", ["60%", "40%", "32.5%"]),
            (150, "60%", ["150%", "50%", "66.67%"]),
        ]
        x, correct_ans, distractors = rng.choice(dataset)
        question_text = (
            f"If A's income is {x}% more than B's income, "
            f"by what percentage is B's income less than A's income?"
        )
        solution_steps = (
            f"1. Let B's income = 100.\n"
            f"2. A's income = 100 + {x} = {100 + x}.\n"
            f"3. Difference between A and B = {x}.\n"
            f"4. Percentage B is less than A = ({x} / {100 + x}) * 100% = {correct_ans}."
        )

    elif template_type == 1:
        dataset = [
            (20, "25%", ["20%", "30%", "16.67%"]),
            (25, "33.33%", ["25%", "50%", "20%"]),
            (50, "100%", ["50%", "75%", "150%"]),
            (10, "11.11%", ["10%", "12.5%", "9.09%"]),
            (75, "300%", ["75%", "150%", "250%"]),
        ]
        x, correct_ans, distractors = rng.choice(dataset)
        question_text = (
            f"If A's salary is {x}% less than B's salary, "
            f"by what percentage is B's salary more than A's salary?"
        )
        solution_steps = (
            f"1. Let B's salary = 100.\n"
            f"2. A's salary = 100 - {x} = {100 - x}.\n"
            f"3. Difference between B and A = {x}.\n"
            f"4. Percentage B is more than A = ({x} / {100 - x}) * 100% = {correct_ans}."
        )

    elif template_type == 2:
        dataset = [
            (25, "20%", ["25%", "15%", "22.5%"]),
            (20, "16.67%", ["20%", "25%", "14.28%"]),
            (50, "33.33%", ["50%", "25%", "35%"]),
            (60, "37.5%", ["60%", "40%", "30%"]),
        ]
        x, correct_ans, distractors = rng.choice(dataset)
        question_text = (
            f"If the price of petrol increases by {x}%, by what percentage must a motorist "
            f"reduce consumption so that total expenditure remains unchanged?"
        )
        solution_steps = (
            f"1. Let initial price = P and initial consumption = C.\n"
            f"2. Increased price P' = P * (1 + {x}/100).\n"
            f"3. Constant expenditure requires new consumption C' = C / (1 + {x}/100).\n"
            f"4. Required percentage reduction = ({x} / {100 + x}) * 100% = {correct_ans}."
        )

    else:
        dataset = [
            (10, "1% decrease", ["1% increase", "0% (no change)", "2% decrease"]),
            (20, "4% decrease", ["4% increase", "0% (no change)", "2% decrease"]),
            (30, "9% decrease", ["9% increase", "0% (no change)", "6% decrease"]),
            (25, "6.25% decrease", ["6.25% increase", "0% (no change)", "5% decrease"]),
            (50, "25% decrease", ["25% increase", "0% (no change)", "20% decrease"]),
        ]
        x, correct_ans, distractors = rng.choice(dataset)
        question_text = (
            f"The price of an article is first increased by {x}% and then decreased by {x}%. "
            f"What is the net percentage change in price?"
        )
        solution_steps = (
            f"1. Net percentage change = (+{x}) + (-{x}) + (({x} * (-{x})) / 100)%.\n"
            f"2. Net change = -({x}^2 / 100)% = -{correct_ans.split()[0]}.\n"
            f"3. Hence, there is a net {correct_ans}."
        )

    options, correct_idx = _build_options(correct_ans, distractors, rng)

    return AptitudeProblem(
        id=problem_id,
        category="Percentage",
        question_text=question_text,
        options=options,
        correct_index=correct_idx,
        solution_steps=solution_steps,
    )


def generate_speed_time_drill(seed: int | None = None) -> AptitudeProblem:
    """Generates a speed, time & distance drill with integer arithmetic (SEC-20)."""
    rng = random.Random(seed)  # noqa: S311
    problem_num = rng.randint(1000, 9999) if seed is None else _stable_problem_num(seed, "speed")
    problem_id = f"drill_st_{problem_num}"

    template_type = rng.choice([0, 1, 2, 3])

    if template_type == 0:
        scenarios = [
            (72, 20, 200, 300, 25),  # D=500, v=20 -> T=25s
            (54, 15, 180, 270, 30),  # D=450, v=15 -> T=30s
            (36, 10, 150, 150, 30),  # D=300, v=10 -> T=30s
            (90, 25, 250, 350, 24),  # D=600, v=25 -> T=24s
            (108, 30, 240, 360, 20),  # D=600, v=30 -> T=20s
        ]
        speed_kmh, speed_ms, l_train, l_plat, time_s = rng.choice(scenarios)
        correct_ans = f"{time_s} seconds"
        distractors = [
            f"{time_s - 5} seconds",
            f"{time_s + 5} seconds",
            f"{time_s + 10} seconds",
        ]
        question_text = (
            f"A train {l_train} m long is running at a speed of {speed_kmh} km/h. "
            f"How much time will it take to cross a platform of length {l_plat} m?"
        )
        total_d = l_train + l_plat
        solution_steps = (
            f"1. Convert speed from km/h to m/s: Speed = {speed_kmh} * (5/18) = {speed_ms} m/s.\n"
            f"2. Distance = Train + Platform = {l_train} + {l_plat} = {total_d} m.\n"
            f"3. Time taken = Distance / Speed = {total_d} / {speed_ms} = {time_s} seconds."
        )

    elif template_type == 1:
        scenarios = [
            (54, 15, 20, 300),  # v=15, T=20 -> L=300m
            (72, 20, 15, 300),  # v=20, T=15 -> L=300m
            (36, 10, 18, 180),  # v=10, T=18 -> L=180m
            (90, 25, 12, 300),  # v=25, T=12 -> L=300m
            (108, 30, 14, 420),  # v=30, T=14 -> L=420m
        ]
        speed_kmh, speed_ms, time_s, l_train = rng.choice(scenarios)
        correct_ans = f"{l_train} m"
        distractors = [
            f"{l_train - 50} m",
            f"{l_train + 50} m",
            f"{l_train + 100} m",
        ]
        question_text = (
            f"A train running at a speed of {speed_kmh} km/h crosses an electric pole "
            f"in {time_s} seconds. What is the length of the train?"
        )
        solution_steps = (
            f"1. Convert speed to m/s: Speed = {speed_kmh} * (5/18) = {speed_ms} m/s.\n"
            f"2. To pass a stationary pole, the train covers its own length.\n"
            f"3. Train length = Speed * Time = {speed_ms} * {time_s} = {l_train} m."
        )

    elif template_type == 2:
        scenarios = [
            (180, 270, 30, 15, 54),  # D=450, T=30 -> v=15 m/s -> V=54 km/h
            (200, 300, 25, 20, 72),  # D=500, T=25 -> v=20 m/s -> V=72 km/h
            (150, 150, 30, 10, 36),  # D=300, T=30 -> v=10 m/s -> V=36 km/h
            (250, 350, 24, 25, 90),  # D=600, T=24 -> v=25 m/s -> V=90 km/h
        ]
        l_train, l_plat, time_s, speed_ms, speed_kmh = rng.choice(scenarios)
        correct_ans = f"{speed_kmh} km/h"
        distractors = [
            f"{speed_kmh - 18} km/h",
            f"{speed_kmh + 18} km/h",
            f"{speed_kmh + 36} km/h",
        ]
        question_text = (
            f"A train {l_train} m long crosses a platform {l_plat} m long in {time_s} seconds. "
            f"What is the speed of the train in km/h?"
        )
        total_d = l_train + l_plat
        solution_steps = (
            f"1. Distance = Train + Platform = {l_train} + {l_plat} = {total_d} m.\n"
            f"2. Speed in m/s = Distance / Time = {total_d} / {time_s} = {speed_ms} m/s.\n"
            f"3. Convert m/s to km/h: Speed = {speed_ms} * (18/5) = {speed_kmh} km/h."
        )

    else:
        scenarios = [
            (72, 20, 200, 25, 300),  # v=20, T=25, D=500, L_train=200 -> L_plat=300m
            (54, 15, 180, 30, 270),  # v=15, T=30, D=450, L_train=180 -> L_plat=270m
            (36, 10, 120, 30, 180),  # v=10, T=30, D=300, L_train=120 -> L_plat=180m
            (90, 25, 220, 20, 280),  # v=25, T=20, D=500, L_train=220 -> L_plat=280m
        ]
        speed_kmh, speed_ms, l_train, time_s, l_plat = rng.choice(scenarios)
        correct_ans = f"{l_plat} m"
        distractors = [
            f"{l_plat - 50} m",
            f"{l_plat + 50} m",
            f"{l_plat + 100} m",
        ]
        question_text = (
            f"A train {l_train} m long running at a speed of {speed_kmh} km/h "
            f"crosses a platform in {time_s} seconds. What is the length of the platform?"
        )
        dist_covered = speed_ms * time_s
        solution_steps = (
            f"1. Speed in m/s = {speed_kmh} * (5/18) = {speed_ms} m/s.\n"
            f"2. Distance in {time_s}s = Speed * Time = {speed_ms} * {time_s} = {dist_covered} m.\n"
            f"3. Platform = Distance - Train = {dist_covered} - {l_train} = {l_plat} m."
        )

    options, correct_idx = _build_options(correct_ans, distractors, rng)

    return AptitudeProblem(
        id=problem_id,
        category="Speed, Time & Distance",
        question_text=question_text,
        options=options,
        correct_index=correct_idx,
        solution_steps=solution_steps,
    )


def generate_number_series_drill(seed: int | None = None) -> AptitudeProblem:
    """Generates an algorithmic number series drill with ground truth (SEC-20)."""
    rng = random.Random(seed)  # noqa: S311
    problem_num = rng.randint(1000, 9999) if seed is None else _stable_problem_num(seed, "series")
    problem_id = f"drill_ns_{problem_num}"

    series_type = rng.choice([0, 1, 2, 3])

    if series_type == 0:
        a = rng.choice([3, 5, 7, 8, 11, 14])
        d = rng.choice([3, 4, 5, 6, 7, 9])
        terms = [a + i * d for i in range(5)]
        next_term = a + 5 * d
        correct_ans = str(next_term)
        distractors = [
            str(next_term - d),
            str(next_term + d),
            str(next_term + 2 * d),
        ]
        question_text = f"Find the next term in the series: {', '.join(map(str, terms))}, ?"
        solution_steps = (
            f"1. Calculate differences between consecutive terms:\n"
            f"   {terms[1]} - {terms[0]} = {d}\n"
            f"   {terms[2]} - {terms[1]} = {d}\n"
            f"   {terms[3]} - {terms[2]} = {d}\n"
            f"   {terms[4]} - {terms[3]} = {d}\n"
            f"2. The series is an Arithmetic Progression with common difference d = {d}.\n"
            f"3. Next term = {terms[4]} + {d} = {next_term}."
        )

    elif series_type == 1:
        a = rng.choice([2, 3, 4, 5])
        r = rng.choice([2, 3])
        length = 5 if r == 2 else 4
        terms = [a * (r**i) for i in range(length)]
        next_term = a * (r**length)
        correct_ans = str(next_term)
        distractors = [
            str(next_term - terms[-1]),
            str(next_term + terms[-1]),
            str(next_term + 2 * terms[-1]),
        ]
        question_text = f"Find the next term in the series: {', '.join(map(str, terms))}, ?"
        solution_steps = (
            f"1. Calculate ratios between consecutive terms:\n"
            f"   {terms[1]} / {terms[0]} = {r}\n"
            f"   {terms[2]} / {terms[1]} = {r}\n"
            f"2. The series is a Geometric Progression with common ratio r = {r}.\n"
            f"3. Next term = {terms[-1]} * {r} = {next_term}."
        )

    elif series_type == 2:
        k = rng.choice([2, 3, 4, 5])
        c = rng.choice([0, 1, -1])
        terms = [(k + i) ** 2 + c for i in range(5)]
        next_term = (k + 5) ** 2 + c
        correct_ans = str(next_term)
        distractors = [
            str(next_term - 10),
            str(next_term + 10),
            str(next_term + 20),
        ]
        question_text = f"Find the next term in the series: {', '.join(map(str, terms))}, ?"
        offset_note = f" + {c}" if c > 0 else (f" - {abs(c)}" if c < 0 else "")
        solution_steps = (
            f"1. Analyze each term as a square expression:\n"
            f"   {terms[0]} = {k}^2{offset_note}\n"
            f"   {terms[1]} = {k + 1}^2{offset_note}\n"
            f"   {terms[2]} = {k + 2}^2{offset_note}\n"
            f"   {terms[3]} = {k + 3}^2{offset_note}\n"
            f"   {terms[4]} = {k + 4}^2{offset_note}\n"
            f"2. The pattern follows n^2{offset_note} with n increasing by 1 at each step.\n"
            f"3. Next term = {k + 5}^2{offset_note} = {next_term}."
        )

    else:
        a = rng.choice([2, 4, 5, 7])
        d0 = rng.choice([2, 3, 4])
        delta = rng.choice([2, 3])
        diffs = [d0 + i * delta for i in range(5)]
        terms = [a]
        for diff in diffs[:4]:
            terms.append(terms[-1] + diff)
        next_diff = diffs[4]
        next_term = terms[-1] + next_diff
        correct_ans = str(next_term)
        distractors = [
            str(next_term - delta),
            str(next_term + delta),
            str(next_term + 2 * delta),
        ]
        question_text = f"Find the next term in the series: {', '.join(map(str, terms))}, ?"
        diff_str = ", ".join(map(str, diffs[:4]))
        solution_steps = (
            f"1. Calculate differences between consecutive terms: {diff_str}.\n"
            f"2. The differences form an arithmetic progression increasing by {delta}.\n"
            f"3. Next difference = {diffs[3]} + {delta} = {next_diff}.\n"
            f"4. Next term = {terms[-1]} + {next_diff} = {next_term}."
        )

    options, correct_idx = _build_options(correct_ans, distractors, rng)

    return AptitudeProblem(
        id=problem_id,
        category="Number Series",
        question_text=question_text,
        options=options,
        correct_index=correct_idx,
        solution_steps=solution_steps,
    )
