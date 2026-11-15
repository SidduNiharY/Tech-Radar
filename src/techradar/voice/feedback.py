from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from techradar.english.grammar_check import GrammarIssue
from techradar.voice.metrics import SpeechMetrics
from techradar.voice.pronounce import WordScore


class Fix(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["grammar", "pronunciation", "filler", "pace", "vocabulary"]
    detail: str = Field(max_length=200)
    example: str = Field(max_length=200)


def choose_fixes(
    m: SpeechMetrics,
    issues: Sequence[GrammarIssue],
    words: Sequence[WordScore],
) -> list[Fix]:
    """Select the top 3 actionable speech improvements in strict priority order."""
    candidates: list[Fix] = []

    # 1. Grammar
    if issues:
        rule_counts: dict[str, int] = {}
        for iss in issues:
            key = iss.rule.value if iss.rule else iss.category or "grammar"
            rule_counts[key] = rule_counts.get(key, 0) + 1
        top_r = max(rule_counts.items(), key=lambda x: x[1])[0]
        sample_iss = next(
            (i for i in issues if (i.rule.value if i.rule else i.category) == top_r),
            issues[0],
        )
        candidates.append(
            Fix(
                kind="grammar",
                detail=f"Frequent {top_r} issues ({rule_counts[top_r]} detected)",
                example=sample_iss.message[:180],
            )
        )

    # 2. Pronunciation
    flagged = [w for w in words if w.flagged]
    if flagged:
        lowest = min(flagged, key=lambda w: w.score)
        candidates.append(
            Fix(
                kind="pronunciation",
                detail=f"Work on pronouncing '{lowest.word}' clearly",
                example=f"Score: {lowest.score:.2f} (target >= 0.50)",
            )
        )

    # 3. Fillers
    if m.fillers_per_min > 2.0:
        top_fillers = sorted(m.filler_breakdown.items(), key=lambda x: x[1], reverse=True)
        filler_str = (
            ", ".join(f"'{k}' ({v})" for k, v in top_fillers[:2]) if top_fillers else "fillers"
        )
        candidates.append(
            Fix(
                kind="filler",
                detail=f"High filler rate: {m.fillers_per_min:.1f}/min",
                example=f"Most frequent: {filler_str}",
            )
        )

    # 4. Pace
    if m.words_per_min < 100:
        candidates.append(
            Fix(
                kind="pace",
                detail=f"Pace is slightly slow: {m.words_per_min:.0f} words/min",
                example="Aim for a conversational 120-150 words/min",
            )
        )
    elif m.words_per_min > 170:
        candidates.append(
            Fix(
                kind="pace",
                detail=f"Pace is fast: {m.words_per_min:.0f} words/min",
                example="Slow down to 130-150 words/min to improve clarity",
            )
        )

    # 5. Overused vocabulary
    if m.overused:
        w, count = m.overused[0]
        candidates.append(
            Fix(
                kind="vocabulary",
                detail=f"Word '{w}' was used {count} times",
                example="Try using synonyms to vary your vocabulary",
            )
        )

    return candidates[:3]


class VoiceFeedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: str = Field(max_length=400)
    drill: str = Field(max_length=200)


async def phrase_feedback(
    completer: Any,
    fixes: Sequence[Fix],
    m: SpeechMetrics,
) -> VoiceFeedback:
    """Ask LLM to formulate constructive, concise feedback based on deterministic metrics."""
    if not fixes:
        return VoiceFeedback(
            summary="Great fluency and clarity! Keep maintaining this standard in daily practice.",
            drill="Record a 2-minute spontaneous talk on today's tech news.",
        )

    fixes_text = "\n".join(f"- [{f.kind}] {f.detail}: {f.example}" for f in fixes)
    prompt = (
        f"You are an encouraging English voice coach. Here are speech metrics:\n"
        f"WPM: {m.words_per_min:.1f}, Fillers/min: {m.fillers_per_min:.1f}\n"
        f"Identified priority fixes:\n{fixes_text}\n\n"
        f"Provide a 2-sentence summary and 1 specific actionable drill."
    )
    res = await completer.complete(prompt)
    if isinstance(res, VoiceFeedback):
        return res
    if isinstance(res, dict):
        return VoiceFeedback.model_validate(res)

    # Fallback deterministic parsing
    text = str(res).strip()
    return VoiceFeedback(
        summary=text[:380] if text else "Solid session with clear areas to practice.",
        drill=f"Practice {fixes[0].kind} by repeating phrases slowly."[:190],
    )


def render_voice_report(
    duration_s: float,
    m: SpeechMetrics,
    issues: Sequence[GrammarIssue],
    words: Sequence[WordScore],
    fixes: Sequence[Fix],
    fb: VoiceFeedback,
) -> str:
    """Format voice practice analysis into a structured Telegram report."""
    min_display = f"{duration_s / 60:.1f} min" if duration_s >= 60 else f"{duration_s:.0f}s"
    rate_str = f"{m.fillers_per_min:.1f}/min"
    fluency_line = (
        f"Fluency: {m.words_per_min:.1f} words/min · {m.filler_count} fillers ({rate_str})"
    )

    if issues:
        top_rules = ", ".join(
            dict.fromkeys(i.rule.value if i.rule else i.category for i in issues[:3])
        )
        grammar_line = f"Grammar: {len(issues)} issues · {top_rules}"
    else:
        grammar_line = "Grammar: 0 issues · clean"

    flagged = [w for w in words if w.flagged]
    if flagged:
        pron_items = ", ".join(f"{w.word} ({w.score:.2f})" for w in flagged[:3])
        pron_line = f"Pronunciation: {pron_items}"
    else:
        pron_line = "Pronunciation: clear"

    if m.overused:
        overused_str = ", ".join(f"'{w}' ({c}x)" for w, c in m.overused[:3])
        vocab_line = f"Vocabulary: overused {overused_str}"
    else:
        vocab_line = "Vocabulary: good variety"

    if fixes:
        fixes_line = "Top fixes: " + " · ".join(f.detail for f in fixes)
    else:
        fixes_line = "Top fixes: none needed"

    drill_line = f"Next drill: {fb.drill}"

    return (
        f"🎙️ Voice note · {min_display}\n"
        f"{fluency_line}\n"
        f"{grammar_line}\n"
        f"{pron_line}\n"
        f"{vocab_line}\n"
        f"{fixes_line}\n"
        f"{drill_line}"
    )
