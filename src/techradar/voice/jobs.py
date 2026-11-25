"""The voice analysis job and the 24-hour audio deletion (Phase 6 Tasks 1 and 6).

SEC: SEC-15, SEC-17, SEC-18, SEC-57.
"""

from __future__ import annotations

import os
from collections.abc import Callable
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
from techradar.english.grammar_check import check_grammar
from techradar.intake.owner_files import NAME_RE
from techradar.voice.audio import compute_peaks, decode_audio
from techradar.voice.feedback import (
    choose_fixes,
    phrase_feedback,
    render_voice_report,
)
from techradar.voice.intake import NOT_VOICE_REPLY, RETENTION, voice_file_problem
from techradar.voice.metrics import compute_metrics
from techradar.voice.pronounce import score_words
from techradar.voice.transcribe import no_speech

VOICE_UNAVAILABLE_REPLY = (
    "Voice analysis isn't installed on the server yet. Your recording is deleted within 24 hours."
)


def _unlink_file(path_str: str, voice_dir: Path | None = None) -> None:
    """Remove a stored recording. Never follows a link; with `voice_dir`, only a hash-named
    file directly inside `voice_dir/in` is removed (a path from the database is not trusted
    to point anywhere else)."""
    p = Path(path_str)
    if voice_dir is not None:
        in_dir = voice_dir / "in"
        if p.parent != in_dir or not NAME_RE.fullmatch(p.name):
            return
        try:
            dfd = os.open(in_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return
        try:
            os.unlink(p.name, dir_fd=dfd)
        except FileNotFoundError:
            pass
        finally:
            os.close(dfd)
        return
    p.unlink(missing_ok=True)  # unlink removes a link itself, never its target


def _unlink_reply(voice_dir: Path, session_id: int) -> None:
    """Remove the generated spoken reply of a session, if any (never through a link)."""
    try:
        dfd = os.open(voice_dir / "out", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return
    try:
        os.unlink(f"reply_{int(session_id)}.ogg", dir_fd=dfd)
    except FileNotFoundError:
        pass
    finally:
        os.close(dfd)


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
    lt_client: Any | None = None,
    lt_url: str = "http://languagetool:8010",
    voice_dir: Path | None = None,
    free_gpu_fn: Any | None = None,
    probe: Callable[[Path], str | None] = voice_file_problem,
) -> None:
    """Analyze a voice session: transcribe, compute metrics, score phonemes, and report.

    `probe` checks the stored file before anything decodes it (a real Ogg voice note within
    the limits, ffprobe with `-protocol_whitelist file`); anything else is refused.
    """
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

    # 0. The file must still be a real Ogg voice note (SEC-57)
    if await anyio.to_thread.run_sync(probe, audio_path) is not None:
        voice_row.status = "failed"
        await session.commit()
        if outbox is not None:
            await outbox.send_text(NOT_VOICE_REPLY)
        return

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
    if lt_client is not None:
        issues = await check_grammar(lt_client, lt_url, transcript.text)

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
        speaker.speak(fb.summary, out_voice_path)

    if outbox is not None:
        await outbox.send_text(
            report_text,
            button={"text": "Keep recording", "data": f"keep_voice:{voice_row.id}"},
        )


async def mark_voice_unavailable(
    session: AsyncSession, session_id: int, now: datetime | None = None
) -> bool:
    """No transcriber on this server: the session fails and its audio keeps the 24-hour limit.

    Returns False if the session does not exist (nothing to tell the owner).
    """
    voice_row = await session.get(VoiceSession, session_id)
    if voice_row is None:
        return False
    limit = (now or datetime.now(UTC)) + RETENTION
    voice_row.status = "failed"
    if voice_row.delete_after is None or voice_row.delete_after > limit:
        voice_row.delete_after = limit
    await session.flush()
    return True


async def cleanup_voice(
    session: AsyncSession, now: datetime | None = None, *, voice_dir: Path | None = None
) -> int:
    """Purge expired voice recordings that were not marked 'kept'.

    Deletes the input audio (and, with `voice_dir`, the generated spoken reply) of every
    session past `delete_after` unless kept, and nulls `audio_path`. A file that another
    session still needs (kept, or not yet expired: the same note sent twice is one file) is
    left in place.
    """
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
            still_needed = (
                await session.execute(
                    select(VoiceSession.id)
                    .where(VoiceSession.audio_path == s.audio_path)
                    .where(VoiceSession.id != s.id)
                    .where(
                        VoiceSession.kept.is_(True)
                        | VoiceSession.delete_after.is_(None)
                        | (VoiceSession.delete_after > current_time)
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if still_needed is None:
                await anyio.to_thread.run_sync(_unlink_file, s.audio_path, voice_dir)
            if voice_dir is not None:
                await anyio.to_thread.run_sync(_unlink_reply, voice_dir, s.id)
            s.audio_path = None
            cleaned += 1

    await session.commit()
    return cleaned
