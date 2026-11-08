from __future__ import annotations

import random
import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def reject_links(value: str) -> str:
    if _LINK_RE.search(value):
        raise ValueError("links are not allowed")
    return value


NoLinks = Annotated[str, AfterValidator(reject_links)]


class MCQOption(BaseModel):
    text: str
    option_id: str


class MCQDraft(BaseModel):
    question: Annotated[
        str,
        Field(min_length=10, max_length=300),
        AfterValidator(reject_links),
    ]
    options: list[
        Annotated[
            str,
            Field(min_length=1, max_length=120),
            AfterValidator(reject_links),
        ]
    ]
    answer_index: Annotated[int, Field(ge=0, le=3)]
    explanation: Annotated[
        str,
        Field(max_length=400),
        AfterValidator(reject_links),
    ] = ""

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("options must contain exactly 4 items")
        if len(set(v)) != len(v):
            raise ValueError("options must be unique")
        return v

    @field_validator("answer_index")
    @classmethod
    def validate_answer_index(cls, v: int) -> int:
        if v < 0 or v > 3:
            raise ValueError("answer_index must be between 0 and 3")
        return v


def shuffle_options(draft: MCQDraft, seed: int) -> MCQDraft:
    """Deterministically shuffles options while tracking the correct answer index."""
    rng = random.Random(seed)  # noqa: S311
    indexed_options = list(enumerate(draft.options))
    rng.shuffle(indexed_options)

    new_options = [opt for _, opt in indexed_options]
    new_answer_index = next(
        new_idx
        for new_idx, (orig_idx, _) in enumerate(indexed_options)
        if orig_idx == draft.answer_index
    )
    return draft.model_copy(
        update={
            "options": new_options,
            "answer_index": new_answer_index,
        }
    )
