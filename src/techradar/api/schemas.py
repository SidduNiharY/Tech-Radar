from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from techradar.briefing.compose import Section


class TodayItem(BaseModel):
    """A briefing item summary for the daily overview dashboard."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: int | str
    title: str
    section: str
    exam_tags: list[str] = Field(default_factory=list)
    verified_headline: str | None = None
    four_questions: list[str] = Field(default_factory=list)
    note_path: str


class TodayResponse(BaseModel):
    """Daily dashboard response including items and revision plan."""

    model_config = ConfigDict(extra="forbid")

    date: date
    items: list[TodayItem] = Field(default_factory=list)
    plan_lines: list[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    """User question submitted to RAG pipeline."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(min_length=1, max_length=500)]
    verified_only: bool = False


class AskResponse(BaseModel):
    """Response returned upon enqueuing an ask question."""

    model_config = ConfigDict(extra="forbid")

    answer_id: int


class Answer(BaseModel):
    """Completed RAG answer with citations."""

    model_config = ConfigDict(extra="forbid")

    id: int
    question: str
    answer: str
    citations: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class AnswerStatus(BaseModel):
    """Status polling response for an asynchronous question."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "answered", "not_found", "needs_review"]
    answer: Answer | None = None


class CardOut(BaseModel):
    """Spaced repetition flashcard prompt for practice review."""

    model_config = ConfigDict(extra="forbid")

    id: int
    front: str


class CardBackResponse(BaseModel):
    """Revealed flashcard answer content."""

    model_config = ConfigDict(extra="forbid")

    back: str


class RateCardRequest(BaseModel):
    """Rating submitted for FSRS flashcard scheduling."""

    model_config = ConfigDict(extra="forbid")

    rating: Annotated[int, Field(ge=1, le=4)]


class RateCardResponse(BaseModel):
    """Next scheduled review timestamp for a rated flashcard."""

    model_config = ConfigDict(extra="forbid")

    next_due: datetime


class QuizQuestion(BaseModel):
    """Multiple choice question presented without answer key."""

    model_config = ConfigDict(extra="forbid")

    mcq_id: int
    question: str
    options: list[str] = Field(min_length=2, max_length=4)


class AnswerQuizRequest(BaseModel):
    """Selected option index for a quiz question."""

    model_config = ConfigDict(extra="forbid")

    chosen: Annotated[int, Field(ge=0, le=3)]


class AnswerOutcome(BaseModel):
    """Feedback outcome for a submitted quiz answer."""

    model_config = ConfigDict(extra="forbid")

    correct: bool
    chosen: int
    answer_index: int
    explanation: str
    card_created: bool = False


class LoadedModel(BaseModel):
    """VRAM and memory statistics for an active LLM in Ollama."""

    model_config = ConfigDict(extra="forbid")

    name: str
    size_bytes: int
    size_vram_bytes: int


class ModelsStatus(BaseModel):
    """System model runtime and host memory status."""

    model_config = ConfigDict(extra="forbid")

    roles: dict[str, str]
    loaded: list[LoadedModel] = Field(default_factory=list)
    ram_total_bytes: int
    ram_available_bytes: int


class UserSettings(BaseModel):
    """Configurable user preferences and schedule defaults."""

    model_config = ConfigDict(extra="forbid")

    briefing_time: Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
    sections: list[Section | str] = Field(min_length=1)
    verified_only_default: bool = False


class Ticket(BaseModel):
    """Confirmation ticket for two-step verification."""

    model_config = ConfigDict(extra="forbid")

    id: int
    token: str
    summary: str
    expires_at: datetime
