"""Nightly pattern detection in plain code for feedback and self-improvement."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PreferenceRule


class Mode(StrEnum):
    """Supported study, exam, and content modes."""

    GATE = "gate"
    SSC_GK = "ssc_gk"
    BANK = "bank"
    ECONOMY = "economy"
    NEWS = "news"
    TECH = "tech"
    ENGLISH = "english"


class Evidence(BaseModel):
    """Audit evidence supporting a proposed pattern rule."""

    ids: list[int] = Field(default_factory=list, max_length=200)
    count: int
    total: int | None = None
    window_days: int
    table: Literal[
        "feedback",
        "action_log",
        "edits",
        "mistakes",
        "study_sessions",
        "quiz_attempts",
    ]


class StyleProposal(BaseModel):
    """Proposed addition or change to user style rules."""

    mode: Mode | None = None
    field: str
    value: str


class WeightProposal(BaseModel):
    """Proposed topic or source weight adjustment."""

    kind: Literal["topic", "source"]
    key: str
    target: float = Field(ge=0.2, le=2.0)


class ContentProposal(BaseModel):
    """Proposed learning content creation to resolve confusion or repeated mistakes."""

    kind: Literal["foundation_page", "comparison_card", "plan_block", "focused_revision"]
    subject: str = Field(max_length=120)


class PatternCandidate(BaseModel):
    """Detected behavioral pattern with proposal and verifiable evidence."""

    kind: Literal[
        "frequency",
        "source",
        "sequence",
        "confusion",
        "mistakes",
        "time",
        "edit",
        "pairs",
    ]
    subject: str = Field(max_length=120)
    evidence: Evidence
    proposal: StyleProposal | WeightProposal | ContentProposal


# --- Pure pattern detection functions ---


def frequency_candidates(
    items: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect topics where >70% of at least 10 presented items were skipped."""
    by_topic: dict[str, list[Any]] = {}
    for item in items:
        topic = getattr(item, "topic", None) or (
            item.get("topic") if isinstance(item, dict) else None
        )
        if topic:
            by_topic.setdefault(topic, []).append(item)

    candidates: list[PatternCandidate] = []
    for topic, topic_items in by_topic.items():
        total = len(topic_items)
        if total < 10:
            continue
        skips = [
            it
            for it in topic_items
            if (
                getattr(it, "kind", None) == "skip"
                or (isinstance(it, dict) and it.get("kind") == "skip")
            )
        ]
        skip_count = len(skips)
        if (skip_count / total) > 0.70:
            ids = [getattr(it, "id", i) for i, it in enumerate(skips, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="frequency",
                    subject=f"Frequent skips on {topic}",
                    evidence=Evidence(
                        ids=ids,
                        count=skip_count,
                        total=total,
                        window_days=window_days,
                        table="action_log",
                    ),
                    proposal=WeightProposal(
                        kind="topic",
                        key=f"section:{topic}",
                        target=0.5,
                    ),
                )
            )
    return candidates


def source_candidates(
    feedback_rows: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect sources with >=5 negative signals (down, wrong, wrong_source)."""
    by_source: dict[str, list[Any]] = {}
    for fb in feedback_rows:
        sig = getattr(fb, "signal", None) or (fb.get("signal") if isinstance(fb, dict) else None)
        src = getattr(fb, "source", None) or (fb.get("source") if isinstance(fb, dict) else None)
        if sig in {"down", "wrong", "wrong_source"} and src:
            by_source.setdefault(src, []).append(fb)

    candidates: list[PatternCandidate] = []
    for src, rows in by_source.items():
        if len(rows) >= 5:
            ids = [getattr(r, "id", i) for i, r in enumerate(rows, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="source",
                    subject=f"Negative feedback on source {src}",
                    evidence=Evidence(
                        ids=ids,
                        count=len(rows),
                        total=None,
                        window_days=window_days,
                        table="feedback",
                    ),
                    proposal=WeightProposal(
                        kind="source",
                        key=f"source:{src}",
                        target=0.5,
                    ),
                )
            )
    return candidates


def sequence_candidates(
    answers_with_follow_ups: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect follow-up sequences indicating need for examples or depth adjustment."""
    by_mode: dict[str, list[Any]] = {}
    for item in answers_with_follow_ups:
        mode_val = getattr(item, "mode", None) or (
            item.get("mode") if isinstance(item, dict) else None
        )
        if mode_val:
            by_mode.setdefault(str(mode_val), []).append(item)

    candidates: list[PatternCandidate] = []
    for mode_str, items in by_mode.items():
        if len(items) < 5:
            continue
        try:
            m = Mode(mode_str)
        except ValueError:
            m = None

        texts = [
            (
                getattr(it, "text", "") or (it.get("text", "") if isinstance(it, dict) else "")
            ).lower()
            for it in items
        ]

        example_matches = [it for it, txt in zip(items, texts, strict=False) if "example" in txt]
        simpler_matches = [it for it, txt in zip(items, texts, strict=False) if "simpler" in txt]
        deeper_matches = [
            it for it, txt in zip(items, texts, strict=False) if "why" in txt or "deeper" in txt
        ]

        if len(example_matches) >= 5:
            ids = [getattr(it, "id", i) for i, it in enumerate(example_matches, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="sequence",
                    subject=f"Repeated example requests in {mode_str}",
                    evidence=Evidence(
                        ids=ids,
                        count=len(example_matches),
                        total=len(items),
                        window_days=window_days,
                        table="action_log",
                    ),
                    proposal=StyleProposal(mode=m, field="examples", value="one"),
                )
            )
        elif len(simpler_matches) >= 5:
            ids = [getattr(it, "id", i) for i, it in enumerate(simpler_matches, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="sequence",
                    subject=f"Requests for simpler explanations in {mode_str}",
                    evidence=Evidence(
                        ids=ids,
                        count=len(simpler_matches),
                        total=len(items),
                        window_days=window_days,
                        table="action_log",
                    ),
                    proposal=StyleProposal(mode=m, field="depth", value="simpler"),
                )
            )
        elif len(deeper_matches) >= 5:
            ids = [getattr(it, "id", i) for i, it in enumerate(deeper_matches, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="sequence",
                    subject=f"Requests for deeper explanations in {mode_str}",
                    evidence=Evidence(
                        ids=ids,
                        count=len(deeper_matches),
                        total=len(items),
                        window_days=window_days,
                        table="action_log",
                    ),
                    proposal=StyleProposal(mode=m, field="depth", value="deeper"),
                )
            )
    return candidates


def edit_candidates(
    edit_rows: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect edits repeatedly removing sections or shortening notes."""
    removed_counter: Counter[str] = Counter()
    removed_ids: dict[str, list[int]] = {}
    shortening_edits: list[Any] = []

    for idx, e in enumerate(edit_rows, 1):
        eid = getattr(e, "id", idx)
        secs = getattr(e, "sections_removed", None) or (
            e.get("sections_removed") if isinstance(e, dict) else []
        )
        for s in secs:
            removed_counter[s] += 1
            removed_ids.setdefault(s, []).append(eid)

        len_ch = getattr(e, "length_change", 0) or (
            e.get("length_change", 0) if isinstance(e, dict) else 0
        )
        if len_ch < -200:
            shortening_edits.append(e)

    candidates: list[PatternCandidate] = []
    for sec, count in removed_counter.items():
        if count >= 5:
            candidates.append(
                PatternCandidate(
                    kind="edit",
                    subject=f"Repeatedly removing section {sec}",
                    evidence=Evidence(
                        ids=removed_ids[sec][:200],
                        count=count,
                        total=None,
                        window_days=window_days,
                        table="edits",
                    ),
                    proposal=StyleProposal(
                        mode=None,
                        field="skip_section",
                        value=sec,
                    ),
                )
            )

    if len(shortening_edits) >= 5:
        ids = [getattr(e, "id", i) for i, e in enumerate(shortening_edits, 1)][:200]
        candidates.append(
            PatternCandidate(
                kind="edit",
                subject="Repeated note shortening edits",
                evidence=Evidence(
                    ids=ids,
                    count=len(shortening_edits),
                    total=len(edit_rows),
                    window_days=window_days,
                    table="edits",
                ),
                proposal=StyleProposal(
                    mode=None,
                    field="length",
                    value="short",
                ),
            )
        )

    return candidates


def mistakes_candidates(
    mistake_rows: Sequence[Any],
    window_days: int = 30,
) -> list[PatternCandidate]:
    """Detect subjects or chapters with >=3 wrong answers in 30 days."""
    by_subject: dict[str, list[Any]] = {}
    for m in mistake_rows:
        subj = getattr(m, "subject", None) or (m.get("subject") if isinstance(m, dict) else None)
        if subj:
            by_subject.setdefault(subj, []).append(m)

    candidates: list[PatternCandidate] = []
    for subj, rows in by_subject.items():
        if len(rows) >= 3:
            ids = [getattr(r, "id", i) for i, r in enumerate(rows, 1)][:200]
            candidates.append(
                PatternCandidate(
                    kind="mistakes",
                    subject=f"Repeated mistakes in {subj}",
                    evidence=Evidence(
                        ids=ids,
                        count=len(rows),
                        total=None,
                        window_days=window_days,
                        table="mistakes",
                    ),
                    proposal=ContentProposal(
                        kind="focused_revision",
                        subject=subj[:120],
                    ),
                )
            )
    return candidates


def time_candidates(
    session_rows: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect session patterns and propose nearest standard block length (25, 45, 60m)."""
    if len(session_rows) < 7:
        return []

    durations: list[float] = []
    ids: list[int] = []
    for idx, s in enumerate(session_rows, 1):
        ids.append(getattr(s, "id", idx))
        dur = getattr(s, "minutes", None) or (s.get("minutes") if isinstance(s, dict) else 30.0)
        durations.append(float(dur))

    durations.sort()
    mid = len(durations) // 2
    median = (
        durations[mid] if len(durations) % 2 != 0 else (durations[mid - 1] + durations[mid]) / 2.0
    )

    targets = [25, 45, 60]
    nearest = min(targets, key=lambda t: abs(t - median))

    return [
        PatternCandidate(
            kind="time",
            subject=f"Session block length optimal around {nearest}m",
            evidence=Evidence(
                ids=ids[:200],
                count=len(session_rows),
                total=None,
                window_days=window_days,
                table="study_sessions",
            ),
            proposal=StyleProposal(
                mode=None,
                field="block_minutes",
                value=str(nearest),
            ),
        )
    ]


def pairs_candidates(
    pair_rows: Sequence[Any],
    window_days: int = 14,
) -> list[PatternCandidate]:
    """Detect >=5 choices of the same variant in a mode from Which-is-better pairs."""
    counts: dict[tuple[str, str, str], list[int]] = {}
    for idx, p in enumerate(pair_rows, 1):
        pid = getattr(p, "id", idx)
        mode_val = str(
            getattr(p, "mode", "news") or (p.get("mode", "news") if isinstance(p, dict) else "news")
        )
        chosen = getattr(p, "chosen", None) or (p.get("chosen") if isinstance(p, dict) else None)
        if chosen in {"a", "b"}:
            variant = getattr(p, f"variant_{chosen}", "") or (
                p.get(f"variant_{chosen}", "") if isinstance(p, dict) else ""
            )
            field_name = "length" if variant in {"short", "detailed", "long"} else "order"
            counts.setdefault((mode_val, field_name, variant), []).append(pid)

    candidates: list[PatternCandidate] = []
    for (m_str, fld, var), ids in counts.items():
        if len(ids) >= 5:
            try:
                m = Mode(m_str)
            except ValueError:
                m = None
            candidates.append(
                PatternCandidate(
                    kind="pairs",
                    subject=f"Consistent choice of {var} in {m_str}",
                    evidence=Evidence(
                        ids=ids[:200],
                        count=len(ids),
                        total=None,
                        window_days=window_days,
                        table="feedback",
                    ),
                    proposal=StyleProposal(
                        mode=m,
                        field=fld,
                        value=var,
                    ),
                )
            )
    return candidates


# --- Async pattern runner ---


async def find_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
) -> list[PatternCandidate]:
    """Find candidate patterns and filter out proposals already active."""
    candidates: list[PatternCandidate] = []

    # Filter out candidates already covered by active preference_rules
    active_rules_stmt = select(PreferenceRule).where(PreferenceRule.status == "active")
    res = await session.execute(active_rules_stmt)
    active_rules = res.scalars().all()
    active_keys = {(r.mode, r.field, r.value) for r in active_rules}

    filtered: list[PatternCandidate] = []
    for c in candidates:
        if isinstance(c.proposal, StyleProposal):
            mode_val = c.proposal.mode.value if c.proposal.mode else None
            if (mode_val, c.proposal.field, c.proposal.value) in active_keys:
                continue
        filtered.append(c)

    return filtered


async def run_find_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
) -> list[PatternCandidate]:
    """Execute nightly pattern detection job and return actionable candidates."""
    return await find_patterns(session, embedder=embedder, now=now)


async def find_recurring_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
) -> list[PatternCandidate]:
    """Detect recurring mistakes or high-friction areas."""
    return await find_patterns(session, embedder=embedder, now=now)
