from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    PronunciationScore,
    VoiceMetrics,
    VoiceSession,
)
from techradar.english.grammar_check import GrammarChecker
from techradar.voice.audio import compute_peaks, decode_audio
from techradar.voice.feedback import (
    choose_fixes,
    phrase_feedback,
    render_voice_report,
)
from techradar.voice.metrics import compute_metrics
from techradar.voice.pronounce import score_words
from techradar.voice.transcribe import no_speech


def _unlink_file(path_str: str) -> None:
    p = Path(path_str)
    if p.exists():
        p.unlink(missing_ok=True)


def _file_exists(path_str: str) -> bool:
    return Path(path_str).exists()


async def analyse_voice(
    session: AsyncSession,
    session_id: int,
    *,
    transcriber: Any,
    phoneme_model: Any,
    completer: Any,
    speaker: Any | None = None,
    outbox: Any | None = None,
    grammar: GrammarChecker | None = None,
    voice_dir: Path | None = None,
    free_gpu_fn: Any | None = None,
) -> None:
    """Analyze a voice session: transcribe, compute metrics, score phonemes, and report."""
    if free_gpu_fn is not None:
        await free_gpu_fn()

    stmt = select(VoiceSession).where(VoiceSession.id == session_id)
    res = await session.execute(stmt)
    voice_row = res.scalar_one_or_none()
    if voice_row is None:
        return

    if not voice_row.audio_path or not await anyio.to_thread.run_sync(
        _file_exists, voice_row.audio_path
    ):
        voice_row.status = "failed"
        await session.commit()
        return

    audio_path = Path(voice_row.audio_path)

    # 1. Decode & Peaks
    wav = decode_audio(audio_path)
    peaks = compute_peaks(wav, n=800)
    voice_row.peaks = peaks

    # 2. Transcribe
    transcript = transcriber.transcribe(audio_path)
    voice_row.transcript = transcript.model_dump()

    if no_speech(transcript):
        voice_row.status = "no_speech"
        await session.commit()
        if outbox is not None:
            await outbox.send_text("I couldn't hear speech in that note.")
        return

    # 3. Metrics
    m = compute_metrics(transcript)
    v_metrics = VoiceMetrics(
        session_id=voice_row.id,
        words_per_min=m.words_per_min,
        filler_count=m.filler_count,
        fillers_per_min=m.fillers_per_min,
        filler_breakdown=m.filler_breakdown,
        long_pauses=m.long_pauses,
        avg_sentence_words=m.avg_sentence_words,
        type_token_ratio=m.type_token_ratio,
        overused=m.overused,
    )
    session.add(v_metrics)

    # 4. Grammar
    issues: list[Any] = []
    if grammar is not None:
        issues = await grammar.check(transcript.text)

    # 5. Phonemes / Pronunciation
    word_scores = score_words(wav, transcript.words, phoneme_model)
    for ws in word_scores:
        session.add(
            PronunciationScore(
                session_id=voice_row.id,
                word=ws.word,
                start_s=ws.start_s,
                end_s=ws.end_s,
                score=ws.score,
                flagged=ws.flagged,
            )
        )

    # 6. Fixes & Feedback
    fixes = choose_fixes(m, issues, word_scores)
    fb = await phrase_feedback(completer, fixes, m)

    # 7. Retention: delete after 24h unless kept
    now = datetime.now(UTC)
    voice_row.delete_after = now + timedelta(hours=24)
    voice_row.status = "analysed"
    await session.commit()

    # 8. Render report & Outbox
    report_text = render_voice_report(voice_row.duration_s, m, issues, word_scores, fixes, fb)

    if speaker is not None and voice_dir is not None:
        out_voice_path = voice_dir / "out" / f"reply_{voice_row.id}.ogg"
        await anyio.to_thread.run_sync(speaker.speak, fb.summary, out_voice_path)

    if outbox is not None:
        await outbox.send_text(
            report_text,
            button={"text": "Keep recording", "data": f"keep_voice:{voice_row.id}"},
        )


async def cleanup_voice(session: AsyncSession, now: datetime | None = None) -> int:
    """Purge expired voice recordings that were not marked 'kept'."""
    current_time = now or datetime.now(UTC)
    stmt = (
        select(VoiceSession)
        .where(VoiceSession.kept.is_(False))
        .where(VoiceSession.delete_after.is_not(None))
        .where(VoiceSession.delete_after <= current_time)
        .where(VoiceSession.audio_path.is_not(None))
    )
    res = await session.execute(stmt)
    expired_sessions = res.scalars().all()
    cleaned = 0

    for s in expired_sessions:
        if s.audio_path:
            await anyio.to_thread.run_sync(_unlink_file, s.audio_path)
            s.audio_path = None
            cleaned += 1

    await session.commit()
    return cleaned
