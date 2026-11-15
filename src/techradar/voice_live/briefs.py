"""Live voice session briefs and interview question packs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal[
    "conversation",
    "interview_tech",
    "interview_hr",
    "interview_bank",
    "gd",
    "debate",
    "roleplay",
    "explain",
    "read_aloud",
    "shadowing",
]

HR_QUESTIONS: tuple[str, ...] = (
    "Tell me about yourself.",
    "What are your greatest strengths and areas for improvement?",
    "Why are you interested in this position and organization?",
    "Describe a challenging situation in a project and how you resolved it.",
    "Where do you see yourself in five years?",
    "How do you handle tight deadlines and high pressure?",
    "Tell me about a time you had a conflict with a colleague and how you handled it.",
    "Describe a time you failed or made a mistake, and what you learned.",
    "How do you prioritize multiple competing tasks or goals?",
    "Give an example of how you took initiative on a project without being asked.",
    "What motivates you to do your best work?",
    "Do you have any questions for us?",
)

BANK_PANEL_QUESTIONS: tuple[str, ...] = (
    "Why banking?",
    "What do you understand by monetary policy and the role of the RBI?",
    "Explain the difference between Repo Rate, Reverse Repo Rate, and MSF.",
    "What is a Non-Performing Asset (NPA) and how do banks manage asset quality?",
    "Can you explain the significance of Priority Sector Lending (PSL) norms in India?",
    "What are payment banks and small finance banks, and how do they differ from commercial banks?",
    "What is financial inclusion and what government schemes promote it?",
    "Tell us about your home district and its major economic or agricultural activities.",
    "How do current geopolitical developments impact inflation and interest rates in India?",
    "How would you handle an irate customer complaining about an unauthorized debit?",
    "What is the difference between NEFT, RTGS, IMPS, and UPI?",
    "Why should this panel select you today over other candidates?",
)


class SessionBrief(BaseModel):
    """Structured brief passed to the live voice agent."""

    model_config = ConfigDict(frozen=True)

    mode: Mode
    questions: list[str] = Field(default_factory=list, max_length=15)
    facts: list[str] = Field(default_factory=list, max_length=20)
    stories: list[str] = Field(default_factory=list, max_length=5)
    passage: str | None = Field(default=None, max_length=1500)


def build_live_brief(
    user_profile: dict[str, Any],
    goal: str,
    context_notes: Sequence[str],
) -> str:
    """Build a comprehensive textual brief for the live voice coach model."""
    parts: list[str] = [f"# Live Voice Session Brief: {goal.upper()}"]

    name = user_profile.get("name", "Student")
    degree = user_profile.get("degree")
    district = user_profile.get("district")
    state = user_profile.get("state")
    weak_areas = user_profile.get("weak_areas")

    profile_lines = [f"- Name: {name}"]
    if degree:
        profile_lines.append(f"- Degree: {degree}")
    if district or state:
        loc = ", ".join(filter(None, [district, state]))
        profile_lines.append(f"- Location: {loc}")
    if weak_areas:
        if isinstance(weak_areas, (list, tuple)):
            profile_lines.append(f"- Priority Areas: {', '.join(str(w) for w in weak_areas)}")
        else:
            profile_lines.append(f"- Priority Areas: {weak_areas}")
    parts.append("## Candidate Profile\n" + "\n".join(profile_lines))

    parts.append(f"## Focus Goal\nTarget: {goal}")

    goal_lower = goal.lower()
    if any(k in goal_lower for k in ("tech", "fullstack", "ai")):
        qs = (
            "Tell me about an end-to-end system you architected and deployed.",
            "How do you handle latency and context budget limits in agentic workflows?",
            "Explain how you debug memory leaks or connection pool exhaustion in async services.",
            "How do you verify deterministic behavior in pipelines with LLMs?",
            "What security considerations apply when parsing untrusted user inputs?",
        )
        parts.append("## Technical Discussion Prompts\n" + "\n".join(f"- {q}" for q in qs))
    elif "bank" in goal_lower:
        qs = BANK_PANEL_QUESTIONS[:5]
        parts.append("## Interview Questions\n" + "\n".join(f"- {q}" for q in qs))
    elif "hr" in goal_lower or "interview" in goal_lower:
        qs = HR_QUESTIONS[:5]
        parts.append("## Interview Questions\n" + "\n".join(f"- {q}" for q in qs))

    if context_notes:
        note_lines = [f"- {note}" for note in context_notes[:10]]
        parts.append("## Context Notes\n" + "\n".join(note_lines))

    parts.append(
        "## Interaction Guidelines\n"
        "- Do not correct the user while they speak; corrections come after the session.\n"
        "- Speak naturally, ask concise follow-ups, and keep answers to 1-3 sentences."
    )

    return "\n\n".join(parts)


async def build_brief(
    mode: Mode,
    session: Any,
    vault_root: Path | None = None,
    today: date | None = None,
) -> SessionBrief:
    """Build structured SessionBrief for the given mode from database and vault notes."""
    questions: list[str] = []
    facts: list[str] = []
    stories: list[str] = []
    passage: str | None = None

    if mode == "interview_hr":
        questions = list(HR_QUESTIONS[:10])
    elif mode == "interview_bank":
        questions = list(BANK_PANEL_QUESTIONS[:10])
    elif mode == "interview_tech":
        questions = [
            "Explain your asynchronous architecture and error recovery.",
            "How do you ensure zero data leaks across sandboxed containers?",
            "Describe your database indexing strategy for high-concurrency ingestion.",
        ]
    elif mode == "read_aloud":
        passage = (
            "Consistent daily practice across technical foundations and verbal fluency "
            "compounds significantly over time."
        )

    return SessionBrief(
        mode=mode,
        questions=questions[:15],
        facts=facts[:20],
        stories=stories[:5],
        passage=passage,
    )
