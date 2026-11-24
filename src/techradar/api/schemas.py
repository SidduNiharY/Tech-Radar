"""Request and response models of the `/v1` API (Phase 4 Task 2).

No FastAPI import here: the worker reads `UserSettings` too. Requests forbid unknown fields;
every string and list a client sends is bounded.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from techradar.planner.sessions import Goal
from techradar.schemas.pipeline import Section

__all__ = [
    "Answer",
    "AnswerOutcome",
    "AnswerQuizRequest",
    "AnswerStatus",
    "AskRequest",
    "AskResponse",
    "CardBackResponse",
    "CardOut",
    "CitationOut",
    "FourQuestionsOut",
    "LoadedModel",
    "ModelsStatus",
    "QuizQuestion",
    "RateCardRequest",
    "RateCardResponse",
    "Ticket",
    "TodayItem",
    "TodayResponse",
    "UserSettings",
]

MAX_QUESTION_CHARS = 500


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4096)


# --- today ------------------------------------------------------------------------------


class FourQuestionsOut(_Out):
    """The four questions of a story; empty when the briefing did not store one."""

    what_happened: str = ""
    why: str = ""
    what_changes: str = ""
    how_it_affects_me: str = ""


class TodayItem(_Out):
    """One story of the day's briefing (stored in `briefings.items`)."""

    cluster_id: str
    title: str
    section: Section
    exam_tags: list[str] = Field(default_factory=list)
    verified_headline: bool = False
    four_questions: FourQuestionsOut = Field(default_factory=FourQuestionsOut)
    note_path: str | None = None


class TodayResponse(_Out):
    """The latest briefing (on or before today) and today's plan lines."""

    date: date
    items: list[TodayItem] = Field(default_factory=list)
    plan_lines: list[str] = Field(default_factory=list)


# --- ask --------------------------------------------------------------------------------


class AskRequest(_In):
    """A question for the worker model; blank or over 500 characters is refused."""

    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS),
    ]
    verified_only: bool = False


class AskResponse(_Out):
    answer_id: int


class CitationOut(_Out):
    """A cited note: shown as a source chip, never as a link."""

    n: int
    doc_path: str
    title: str
    heading: str = ""
    verified: bool | None = None


class Answer(_Out):
    """A finished answer: the checked text and its citations."""

    id: int
    question: str
    text: str
    citations: list[CitationOut] = Field(default_factory=list)
    status: Literal["answered", "not_found", "needs_review"]
    used_unverified: bool = False
    created_at: datetime | None = None


class AnswerStatus(_Out):
    """Polling result for an asked question; `answer` is set once it is no longer pending."""

    status: Literal["pending", "answered", "not_found", "needs_review"]
    answer: Answer | None = None


# --- practice ---------------------------------------------------------------------------


class CardOut(_Out):
    """A due flashcard's front; the back is fetched separately."""

    id: int
    front: str


class CardBackResponse(_Out):
    back: str


class RateCardRequest(_In):
    """1 Again, 2 Hard, 3 Good, 4 Easy."""

    rating: Annotated[int, Field(ge=1, le=4, strict=True)]


class RateCardResponse(_Out):
    next_due: datetime


class QuizQuestion(_Out):
    """A multiple-choice question without its answer key."""

    mcq_id: int
    question: str
    options: list[str] = Field(min_length=2, max_length=4)


class AnswerQuizRequest(_In):
    chosen: Annotated[int, Field(ge=0, le=3, strict=True)]


class AnswerOutcome(_Out):
    """Phase 3's `record_answer` outcome; the key is shown only after an answer."""

    correct: bool
    correct_index: int
    explanation: str
    already_answered: bool


# --- models -----------------------------------------------------------------------------


class LoadedModel(_Out):
    """A model Ollama holds in memory (`/api/ps`)."""

    name: str
    size_bytes: int
    size_vram_bytes: int


class ModelsStatus(_Out):
    """Which model does which job, what is loaded, and the host's memory."""

    roles: dict[str, str]
    loaded: list[LoadedModel] = Field(default_factory=list)
    ram_total_bytes: int
    ram_available_bytes: int


# --- settings ---------------------------------------------------------------------------

ExamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class UserSettings(_In):
    """The owner's preferences (one `user_settings` row per field)."""

    briefing_time: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    sections: list[Section] = Field(min_length=1, max_length=len(Section))
    verified_only_default: bool = False
    # Phase 5 (planner).
    exam_priority: list[Goal] = Field(
        default_factory=lambda: [Goal.GOV, Goal.GATE], max_length=len(Goal)
    )
    exam_dates: dict[ExamName, date] = Field(default_factory=dict, max_length=20)
    weekly_targets_min: dict[Goal, Annotated[int, Field(ge=0, le=7 * 24 * 60)]] = Field(
        default_factory=lambda: {
            Goal.DEV: 600,
            Goal.GATE: 300,
            Goal.GOV: 420,
            Goal.CURRENT: 105,
            Goal.ENGLISH: 140,
        }
    )


# --- tickets ----------------------------------------------------------------------------


class Ticket(_Out):
    """Confirmation ticket for two-step verification."""

    id: int
    token: str
    summary: str
    expires_at: datetime
