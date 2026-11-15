from __future__ import annotations

import random
from datetime import date

from techradar.exams.drills.quant import (
    DrillItem,
    gen_average,
    gen_compound_interest,
    gen_percent_change,
    gen_percentage_of,
    gen_profit_loss_percent,
    gen_ratio_share,
    gen_simple_interest,
    gen_time_speed_distance,
    gen_work_together,
)
from techradar.exams.drills.reasoning import (
    gen_coding_decoding,
    gen_direction_sense,
    gen_number_series,
    gen_odd_one_out,
)
from techradar.exams.drills.speed import (
    gen_approximation,
    gen_cube,
    gen_percent_fraction,
    gen_square,
    gen_table,
)
from techradar.exams.drills.typing import TypingScore, score_typing, typing_passage

QUANT_GENERATORS = [
    gen_percentage_of,
    gen_percent_change,
    gen_ratio_share,
    gen_simple_interest,
    gen_compound_interest,
    gen_profit_loss_percent,
    gen_average,
    gen_time_speed_distance,
    gen_work_together,
]

REASONING_GENERATORS = [
    gen_number_series,
    gen_coding_decoding,
    gen_direction_sense,
    gen_odd_one_out,
]


def daily_set(
    day: date,
    n_quant: int = 10,
    n_reasoning: int = 10,
) -> list[DrillItem]:
    """Generate deterministic daily set of aptitude and reasoning drill items."""
    rng = random.Random(day.toordinal())  # noqa: S311

    items: list[DrillItem] = []
    for _ in range(n_quant):
        gen = rng.choice(QUANT_GENERATORS)
        items.append(gen(rng))

    for _ in range(n_reasoning):
        gen = rng.choice(REASONING_GENERATORS)
        items.append(gen(rng))

    return items


__all__ = [
    "QUANT_GENERATORS",
    "REASONING_GENERATORS",
    "DrillItem",
    "TypingScore",
    "daily_set",
    "gen_approximation",
    "gen_average",
    "gen_coding_decoding",
    "gen_compound_interest",
    "gen_cube",
    "gen_direction_sense",
    "gen_number_series",
    "gen_odd_one_out",
    "gen_percent_change",
    "gen_percent_fraction",
    "gen_percentage_of",
    "gen_profit_loss_percent",
    "gen_ratio_share",
    "gen_simple_interest",
    "gen_square",
    "gen_table",
    "gen_time_speed_distance",
    "gen_work_together",
    "score_typing",
    "typing_passage",
]
