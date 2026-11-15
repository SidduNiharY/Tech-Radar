from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from techradar.english.grammar_check import GrammarIssue
from techradar.llm.client import Role, complete_json

MAX_POLISH_CHARS: int = 2000


class Rubric(BaseModel):
    model_config = ConfigDict(frozen=True)

    structure: int = Field(ge=1, le=5)
    grammar: int = Field(ge=1, le=5)
    vocabulary: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)


class _LLMFeedback(BaseModel):
    issues: list[GrammarIssue] = Field(default_factory=list)
    improved: str = Field(max_length=2000)
    reasons: list[str] = Field(max_length=5)
    rubric: Rubric | None = None


class WritingFeedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    issues: list[GrammarIssue]
    improved: str = Field(max_length=2000)
    reasons: list[str] = Field(max_length=5)
    rubric: Rubric | None = None


def route_and_validate_polish(text: str) -> str | None:
    """Validate character budget for /polish requests."""
    if len(text) > MAX_POLISH_CHARS:
        return "Keep it under 2,000 characters."
    return None


async def feedback_on_text(
    text: str,
    kind: Literal["take", "essay", "letter", "polish"],
    lt: Any,
    completer: Any,
) -> WritingFeedback:
    """Evaluate submitted text using LanguageTool and LLM stylistic coaching."""
    # 1. Grammar check
    issues: list[GrammarIssue] = []
    if lt is not None:
        issues = await lt.check(text)

    # 2. Worker LLM stylistic improvement & rubric
    llm_res = await complete_json(
        completer,
        Role.WORKER,
        "You are an English writing coach. Provide constructive style feedback and rubric.",
        f"Provide writing feedback for {kind}:\n{text}",
        _LLMFeedback,
    )

    return WritingFeedback(
        issues=issues or llm_res.issues,
        improved=llm_res.improved,
        reasons=llm_res.reasons,
        rubric=llm_res.rubric,
    )


def render_writing_feedback(fb: WritingFeedback) -> str:
    """Render writing feedback into markdown format."""
    lines: list[str] = ["Improved:", fb.improved, "", "Why:"]
    for r in fb.reasons:
        lines.append(f"• {r}")

    if fb.rubric:
        r = fb.rubric
        rubric_line = (
            f"Structure {r.structure} · Grammar {r.grammar} · "
            f"Vocabulary {r.vocabulary} · Relevance {r.relevance}"
        )
        lines.extend(["", rubric_line])

    return "\n".join(lines)
