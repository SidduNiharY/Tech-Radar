"""Nightly pattern detection in plain code for feedback and self-improvement."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import PreferenceRule
from techradar.schemas.pipeline import NoLinks


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
        "preference_pairs",
        "answers",
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
    subject: NoLinks = Field(max_length=120)


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


# What each "Which is better?" variant name means as a style rule (see feedback/pairs.py).
PAIR_VARIANT_RULES: dict[str, tuple[str, str]] = {
    "short": ("length", "short"),
    "detailed": ("length", "long"),
    "example_first": ("order", "example_first"),
    "definition_first": ("order", "definition_first"),
}

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
                        key=topic if ":" in topic else f"section:{topic}",
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
            mapped = PAIR_VARIANT_RULES.get(variant)
            if mapped is None:
                continue
            counts.setdefault((mode_val, mapped[0], mapped[1]), []).append(pid)

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
                        table="preference_pairs",
                    ),
                    proposal=StyleProposal(
                        mode=m,
                        field=fld,
                        value=var,
                    ),
                )
            )
    return candidates


def confusion_candidates(
    asks: Sequence[tuple[int, str, Sequence[float]]],
    window_days: int = 21,
    threshold: float = 0.80,
) -> list[PatternCandidate]:
    """At least 5 asks in 21 days that are pairwise at least 0.80 alike: one foundation page.

    `asks` are (answer id, question, embedding). The subject is the most common longer word of
    those questions, kept to letters (it never carries a link or markup).
    """
    from techradar.pipeline.filter import cosine

    used: set[int] = set()
    out: list[PatternCandidate] = []
    for i in range(len(asks)):
        if i in used:
            continue
        group = [i]
        for j in range(i + 1, len(asks)):
            if j in used:
                continue
            if all(cosine(asks[k][2], asks[j][2]) >= threshold for k in group):
                group.append(j)
        if len(group) < 5:
            continue
        used.update(group)
        words: Counter[str] = Counter()
        for k in group:
            for w in re.findall(r"[A-Za-z]{4,}", asks[k][1].lower()):
                if w not in _STOPWORDS:
                    words[w] += 1
        subject = words.most_common(1)[0][0] if words else "this topic"
        out.append(
            PatternCandidate(
                kind="confusion",
                subject=f"Repeated questions about {subject}",
                evidence=Evidence(
                    ids=[asks[k][0] for k in group][:200],
                    count=len(group),
                    total=None,
                    window_days=window_days,
                    table="answers",
                ),
                proposal=ContentProposal(kind="foundation_page", subject=subject),
            )
        )
    return out


_STOPWORDS = frozenset(
    "what when where which that this with from have about does give tell explain "
    "mean means they them their your into than then also more some very".split()
)


# --- Async pattern runner ---


class _Row:
    """A tiny record the pure rules read: attributes by name."""

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def _since(now: datetime, days: int) -> datetime:
    return now - timedelta(days=days)


async def _frequency_rows(session: AsyncSession, now: datetime) -> list[_Row]:
    """Each topic of each story briefed in 14 days: a `skip` (real action_log id) or `shown`."""
    from techradar.db.models import ActionLog, Briefing

    since = _since(now, 14)
    briefs = (await session.execute(select(Briefing).where(Briefing.sent_at >= since))).scalars()
    skips = {
        t: i
        for i, t in (
            await session.execute(
                select(ActionLog.id, ActionLog.target).where(
                    ActionLog.kind == "skip", ActionLog.at >= since
                )
            )
        ).all()
    }
    rows: list[_Row] = []
    for b in briefs:
        for it in b.items or []:
            target = f"story:{it.get('cluster_id', '')}"
            for key in it.get("topic_keys") or []:
                if target in skips:
                    rows.append(_Row(id=skips[target], topic=key, kind="skip"))
                else:
                    rows.append(_Row(id=0, topic=key, kind="shown"))
    return rows


async def _source_rows(session: AsyncSession, now: datetime) -> list[_Row]:
    """Negative feedback on stories, with the story's source domain."""
    from techradar.db.models import Feedback, Item

    fb = (
        await session.execute(
            select(Feedback).where(
                Feedback.at >= _since(now, 14),
                Feedback.target_kind == "digest_item",
                Feedback.signal.in_(("down", "wrong", "wrong_source")),
            )
        )
    ).scalars()
    rows: list[_Row] = []
    for f in fb:
        domains = (
            (await session.execute(select(Item.domain).where(Item.cluster_id == f.target_id)))
            .scalars()
            .all()
        )
        for d in sorted(set(domains)):
            rows.append(_Row(id=f.id, signal=f.signal, source=d))
    return rows


async def _sequence_rows(session: AsyncSession, now: datetime) -> list[_Row]:
    """My last 10 asks in each mode; `text` is the class of my follow-up words, if there was one."""
    from techradar.db.models import ActionLog

    asks = (
        await session.execute(
            select(ActionLog)
            .where(ActionLog.kind.in_(("ask", "follow_up")), ActionLog.at >= _since(now, 14))
            .order_by(ActionLog.id.desc())
        )
    ).scalars()
    per_mode: dict[str, list[_Row]] = {}
    for a in asks:
        mode = a.mode or Mode.NEWS.value
        bucket = per_mode.setdefault(mode, [])
        if len(bucket) < 10:
            text = (a.topic or "") if a.kind == "follow_up" else ""
            bucket.append(_Row(id=a.id, mode=mode, text=text))
    return [r for rows in per_mode.values() for r in rows]


async def _mistake_rows(session: AsyncSession, now: datetime) -> list[_Row]:
    """Wrong answers of 30 days, each with the chapter or fact subject of its question."""
    from techradar.db.models import MCQ, Fact, LibraryChapter, Mistake

    rows: list[_Row] = []
    found = await session.execute(select(Mistake).where(Mistake.created_at >= _since(now, 30)))
    for m in found.scalars():
        subject: str | None = None
        if m.kind == "mcq":
            mcq = await session.get(MCQ, m.ref_id)
            if mcq is not None and mcq.chapter_id is not None:
                ch = await session.get(LibraryChapter, mcq.chapter_id)
                subject = ch.title if ch else None
            elif mcq is not None and mcq.fact_id is not None:
                fact = await session.get(Fact, mcq.fact_id)
                subject = fact.subject if fact else None
        elif m.kind == "grammar":
            subject = "grammar"
        if subject:
            rows.append(_Row(id=m.id, subject=subject))
    return rows


async def _ask_vectors(
    session: AsyncSession, embedder: Any, owner_chat_id: int, now: datetime
) -> list[tuple[int, str, Sequence[float]]]:
    """My own questions of 21 days (never a study group's) with their embeddings."""
    from techradar.db.models import Answer

    if embedder is None:
        return []
    asked = (
        await session.execute(
            select(Answer.id, Answer.question)
            .where(Answer.chat_id == owner_chat_id, Answer.created_at >= _since(now, 21))
            .order_by(Answer.id.desc())
            .limit(200)
        )
    ).all()
    if len(asked) < 5:
        return []
    vectors = await embedder.embed([q for _, q in asked])
    return [(i, q, v) for (i, q), v in zip(asked, vectors, strict=True)]


def _covered(c: PatternCandidate, covered: set[tuple[str | None, str, str]]) -> bool:
    """A style proposal an active or already-proposed rule has (never propose it twice)."""
    p = c.proposal
    if isinstance(p, StyleProposal):
        return ((p.mode.value if p.mode else None), p.field, p.value) in covered
    return False


async def find_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
    *,
    owner_chat_id: int | None = None,
) -> list[PatternCandidate]:
    """Run every rule over the stored rows and drop what a rule already covers.

    Plain code, no model call. Evidence ids are real row ids, so `verify_evidence` can re-check
    them later (SEC-48).
    """
    from techradar.db.models import Edit, PreferencePair, StudySession

    ts = now or datetime.now(UTC)
    candidates: list[PatternCandidate] = []
    candidates += frequency_candidates(await _frequency_rows(session, ts))
    candidates += source_candidates(await _source_rows(session, ts))
    candidates += sequence_candidates(await _sequence_rows(session, ts))
    candidates += mistakes_candidates(await _mistake_rows(session, ts))
    edits = await session.execute(select(Edit).where(Edit.at >= _since(ts, 14)))
    candidates += edit_candidates(list(edits.scalars().all()))
    sessions = await session.execute(
        select(StudySession).where(
            StudySession.started_at >= _since(ts, 14), StudySession.minutes.is_not(None)
        )
    )
    candidates += time_candidates(list(sessions.scalars().all()))
    pairs = await session.execute(
        select(PreferencePair).where(
            PreferencePair.answered_at >= _since(ts, 14), PreferencePair.chosen.in_(("a", "b"))
        )
    )
    candidates += pairs_candidates(list(pairs.scalars().all()))
    if owner_chat_id is not None:
        candidates += confusion_candidates(await _ask_vectors(session, embedder, owner_chat_id, ts))

    rules = (
        await session.execute(
            select(PreferenceRule).where(PreferenceRule.status.in_(("active", "proposed")))
        )
    ).scalars()
    covered = {(r.mode, r.field, r.value) for r in rules}
    return [c for c in candidates if not _covered(c, covered)]


async def _lower_source_once(session: AsyncSession, key: str, now: datetime) -> None:
    """Automatic -0.3 on a source with 5 bad signals, at most once in 14 days; it is logged."""
    from techradar.db.models import ImprovementLog
    from techradar.feedback.weights import apply_signal

    recent = (
        await session.execute(
            select(ImprovementLog).where(
                ImprovementLog.kind == "weight",
                ImprovementLog.key == key,
                ImprovementLog.at >= _since(now, 14),
            )
        )
    ).scalars()
    if any((r.after or {}).get("rule") == "source_pattern" for r in recent):
        return
    ids = await apply_signal(session, topics=[], source=key, delta=-0.3, exam_topic=False, now=now)
    for log_id in ids:
        log = await session.get(ImprovementLog, log_id)
        if log is not None:
            log.after = {**(log.after or {}), "rule": "source_pattern"}
    await session.flush()


async def run_find_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
    *,
    owner_chat_id: int | None = None,
) -> list[PatternCandidate]:
    """The nightly job body: find candidates, and lower a bad source once per window."""
    ts = now or datetime.now(UTC)
    found = await find_patterns(session, embedder, ts, owner_chat_id=owner_chat_id)
    for c in found:
        if c.kind == "source" and isinstance(c.proposal, WeightProposal):
            await _lower_source_once(session, c.proposal.key, ts)
    return found


async def find_recurring_patterns(
    session: AsyncSession,
    embedder: Any = None,
    now: datetime | None = None,
) -> list[PatternCandidate]:
    """Alias kept for the first run's callers."""
    return await find_patterns(session, embedder=embedder, now=now)
