from __future__ import annotations

import json

from techradar.english.reading import reading_quiz
from techradar.practice.mcq import MCQDraft
from tests.fakes import FakeCompleter

NOTE: str = "In 1969, Neil Armstrong became the first person to walk on the Moon."

MCQ_VERBATIM = json.dumps(
    MCQDraft(
        question="Who was the first person to walk on the Moon?",
        options=[
            "Neil Armstrong",
            "Buzz Aldrin",
            "Yuri Gagarin",
            "Michael Collins",
        ],
        answer_index=0,
        explanation="Neil Armstrong stepped onto the lunar surface in 1969.",
        answer_quote="Neil Armstrong became the first person to walk on the Moon",
    ).model_dump()
)

MCQ_INVENTED = json.dumps(
    MCQDraft(
        question="Which spacecraft carried the astronauts?",
        options=[
            "Apollo 11",
            "Vostok 1",
            "Gemini 4",
            "Sputnik 1",
        ],
        answer_index=0,
        explanation="Apollo 11 was the mission.",
        answer_quote=None,
    ).model_dump()
)


async def test_reading_quiz_drops_non_verbatim_answers() -> None:
    qs = await reading_quiz(
        NOTE,
        FakeCompleter(
            [
                MCQ_VERBATIM,
                '{"answer_index": 0}',
                MCQ_INVENTED,
                '{"answer_index": 0}',
            ]
        ),
    )
    assert len(qs) == 1
    assert qs[0].options[0] == "Neil Armstrong"
