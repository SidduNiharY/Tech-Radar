from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role

_QUESTION_START = re.compile(r"^\s*Q\.?\s*(\d{1,2})\b", re.IGNORECASE)
_OPTION_START = re.compile(r"^\s*\(([A-D])\)\s*(.*)", re.IGNORECASE)

_SUGGEST_TOPIC_SYSTEM = (
    "You are an academic exam assistant. Suggest the most relevant topic for the question from "
    "the allowed topics list. You must pick exactly one topic from the list, or set topic to ''."
)
_CHECKER_TOPIC_SYSTEM = (
    "You are a verification assistant. Confirm or reject the proposed topic for the question. "
    "If the question belongs to this topic, repeat it. If not, output ''."
)


class QuestionChunk(BaseModel):
    number: int
    text: str
    options: list[str] | None = None


class KeyEntry(BaseModel):
    qtype: Literal["MCQ", "MSQ", "NAT"]
    key: str
    marks: float


class _TopicSuggestion(BaseModel):
    topic: str


def split_questions(text: str) -> list[QuestionChunk]:
    """Split raw paper text into question chunks with optional options."""
    chunks: list[QuestionChunk] = []
    lines = text.splitlines()

    current_num: int | None = None
    current_lines: list[str] = []
    current_options: list[str] = []

    def flush_current() -> None:
        if current_num is not None:
            q_text = "\n".join(current_lines).strip()
            opts = list(current_options) if current_options else None
            chunks.append(
                QuestionChunk(
                    number=current_num,
                    text=q_text,
                    options=opts,
                )
            )

    for line in lines:
        trimmed = line.strip()
        q_match = _QUESTION_START.match(trimmed)
        if q_match:
            flush_current()
            current_num = int(q_match.group(1))
            current_lines = []
            current_options = []
            # Check if there is remaining question text on the same line after Q. X
            rest = trimmed[q_match.end() :].strip()
            if rest:
                current_lines.append(rest)
            continue

        if current_num is None:
            continue

        opt_match = _OPTION_START.match(trimmed)
        if opt_match:
            current_options.append(trimmed)
        elif current_options:
            # Continuation of an option line
            if trimmed:
                current_options[-1] = f"{current_options[-1]} {trimmed}"
        else:
            if trimmed:
                current_lines.append(trimmed)

    flush_current()
    return chunks


def parse_answer_key(text: str) -> dict[int, KeyEntry]:
    """Parse official GATE answer key rows into KeyEntry mapping by question number."""
    result: dict[int, KeyEntry] = {}
    for line in text.splitlines():
        tokens = line.strip().split()
        if len(tokens) < 4:
            continue

        try:
            num = int(tokens[0])
            raw_qtype = tokens[1].upper()
            if raw_qtype not in ("MCQ", "MSQ", "NAT"):
                continue
            qtype: Literal["MCQ", "MSQ", "NAT"] = raw_qtype  # type: ignore[assignment]
            marks = float(tokens[-1])
        except ValueError, IndexError:
            continue

        middle = tokens[2:-1]
        if not middle:
            continue

        if len(middle) == 1:
            key = middle[0]
        else:
            first = middle[0]
            if first.isalpha() and len(first) <= 4 and first.upper() not in ("A", "B", "C", "D"):
                key = " ".join(middle[1:])
            else:
                key = " ".join(middle)

        result[num] = KeyEntry(qtype=qtype, key=key, marks=marks)

    return result


def check_answer(e: KeyEntry, response: str) -> bool:
    """Verify whether a candidate answer matches the official KeyEntry."""
    resp = response.strip()
    if not resp:
        return False

    if e.qtype == "MCQ":
        return resp.upper() == e.key.strip().upper()

    if e.qtype == "MSQ":
        resp_set = {ch.upper() for ch in re.findall(r"[A-Za-z]", resp)}
        key_set = {ch.upper() for ch in re.findall(r"[A-Za-z]", e.key)}
        return len(resp_set) > 0 and resp_set == key_set

    if e.qtype == "NAT":
        try:
            val = float(resp)
        except ValueError:
            return False

        if "to" in e.key.lower():
            parts = e.key.lower().split("to")
            if len(parts) == 2:
                try:
                    low = float(parts[0].strip())
                    high = float(parts[1].strip())
                    return (low - 1e-9) <= val <= (high + 1e-9)
                except ValueError:
                    return False

        try:
            target = float(e.key.strip())
            return math.isclose(val, target, abs_tol=1e-9)
        except ValueError:
            return False

    return False


async def suggest_topic(
    completer: Completer,
    q: QuestionChunk,
    topics: Sequence[str],
) -> str | None:
    """Ask worker model to suggest a syllabus topic and checker to verify."""
    if not topics:
        return None

    allowed_set = set(topics)
    worker_user = f"Question {q.number}:\n{q.text}\n\nAllowed topics:\n" + "\n".join(
        f"- {t}" for t in topics
    )

    worker_res = await complete_json(
        completer,
        Role.WORKER,
        _SUGGEST_TOPIC_SYSTEM,
        worker_user,
        _TopicSuggestion,
    )

    suggested = worker_res.topic.strip()
    if suggested not in allowed_set:
        return None

    checker_user = (
        f"Question {q.number}:\n{q.text}\n\n"
        f"Proposed topic: {suggested}\n"
        f"Does this question belong to this topic? If yes, repeat '{suggested}'. If no, output ''."
    )

    checker_res = await complete_json(
        completer,
        Role.CHECKER,
        _CHECKER_TOPIC_SYSTEM,
        checker_user,
        _TopicSuggestion,
    )

    if checker_res.topic.strip() == suggested:
        return suggested

    return None
