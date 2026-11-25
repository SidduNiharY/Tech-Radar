"""The voice analysis job body (Phase 6 Tasks 1 and 6).

`analyse_voice` takes every engine as an argument (transcriber, phoneme model, speaker, grammar
checker, completer), so it runs here with fakes. The real engines (faster-whisper, wav2vec2,
Kokoro) are loaded by `voice.engines` inside the `voice-worker` container once approved; until
then the worker fails the note through `voice.retention.mark_voice_unavailable`.

The stored note is opened once (`voice.intake.private_voice_copy`: a hash name in `voice/in`, no
link, one link count, within the limit, bytes matching the name) and copied to a private temp
file. `probe` (`voice.intake.voice_file_problem`), decoding and transcription all read that copy
only, so the file checked is the file decoded; the copy is deleted afterwards. Every path that
touches the row sets `delete_after`, so audio never stays for good unless the owner taps Keep.
Deletion itself is `voice.retention` (numpy-free, re-exported here).

SEC: SEC-15, SEC-17, SEC-18, SEC-57.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import (
    PronunciationScore,
    VoiceMetrics,
    VoiceSession,
)
from techradar.english.grammar_check import GrammarChecker, GrammarIssue
from techradar.intake.owner_files import UnsafeFile
from techradar.llm.client import Completer
from techradar.messaging.outbox import Button, enqueue_message
from techradar.voice.audio import compute_peaks, decode_audio
from techradar.voice.feedback import (
    choose_fixes,
    phrase_feedback,
    render_voice_report,
)
from techradar.voice.intake import (
    NOT_VOICE_REPLY,
    private_voice_copy,
    remove_voice_copy,
    voice_file_problem,
)
from techradar.voice.metrics import compute_metrics
from techradar.voice.pronounce import PhonemeModel, score_words
from techradar.voice.retention import (  # noqa: F401  (re-exported for callers and tests)
    RETENTION,
    cleanup_voice,
    keep_voice,
    mark_voice_unavailable,
    reply_path,
)
from techradar.voice.speak import Speaker
from techradar.voice.transcribe import Transcriber, no_speech

logger = logging.getLogger(__name__)

NO_SPEECH_TEXT = "I couldn't hear speech in that note."
FAILED_TEXT = "I couldn't analyse that note. Please try again."
KEEP_BUTTON_TEXT = "Keep recording"


class VoiceOutbox(Protocol):
    async def send_text(self, text: str, button: dict[str, str] | None = None) -> None: ...

    async def send_voice(self, path: Path) -> None: ...


class EnqueueOutbox:
    """`VoiceOutbox` over the real outbox table (the bot sends what is queued)."""

    def __init__(self, session: AsyncSession, chat_id: int) -> None:
        self._session = session
        self._chat_id = chat_id

    async def send_text(self, text: str, button: dict[str, str] | None = None) -> None:
        buttons = [[Button(**button)]] if button else None
        await enqueue_message(
            self._session, self._chat_id, text, purpose="voice_report", buttons=buttons
        )

    async def send_voice(self, path: Path) -> None:
        await enqueue_message(
            self._session,
            self._chat_id,
            "Voice summary",
            purpose="voice_reply",
            kind="voice",
            file_path=str(path),
        )


async def analyse_voice(
    session: AsyncSession,
    session_id: int,
    *,
    transcriber: Transcriber,
    phoneme_model: PhonemeModel,
    completer: Completer,
    speaker: Speaker | None = None,
    outbox: VoiceOutbox | None = None,
    grammar: GrammarChecker | None = None,
    voice_dir: Path,
    free_gpu_fn: Callable[[], Awaitable[Any]] | None = None,
    now: datetime | None = None,
    probe: Callable[[Path], str | None] = voice_file_problem,
) -> None:
    """Free the GPU, then check, transcribe, measure, score, phrase and report one voice note.

    The stored note is read once into a private copy; `probe` checks that copy before anything
    decodes it (a regular Ogg file within the limits, ffprobe with the `ogg` demuxer and
    `-protocol_whitelist file`), and decoding and transcription read the same copy. Anything
    else is refused. Whatever happens, the row gets a `delete_after` 24 hours out, so audio
    never stays for good unless the owner taps Keep.
    """
    if free_gpu_fn is not None:
        await free_gpu_fn()

    voice_row = (
        await session.execute(select(VoiceSession).where(VoiceSession.id == session_id))
    ).scalar_one_or_none()
    if voice_row is None:
        return
    retain_until = (now or datetime.now(UTC)) + RETENTION

    async def finish(status: str, text: str | None) -> None:
        row = await session.get(VoiceSession, session_id) or voice_row
        row.status = status
        row.delete_after = retain_until
        await session.commit()
        if text is not None and outbox is not None:
            await outbox.send_text(text)

    if not voice_row.audio_path:
        await finish("failed", FAILED_TEXT)
        return

    # One open of the stored note (SEC-57): everything below reads the private copy only.
    try:
        copy = await anyio.to_thread.run_sync(private_voice_copy, voice_dir, voice_row.audio_path)
    except UnsafeFile as err:
        if isinstance(err.__cause__, FileNotFoundError):
            await finish("failed", FAILED_TEXT)
        else:
            logger.warning("voice note %s refused before reading: %s", session_id, err)
            await finish("failed", NOT_VOICE_REPLY)
        return
    except Exception:
        logger.exception("voice note %s could not be read", session_id)
        await finish("failed", FAILED_TEXT)
        return

    try:
        # The copy must be a real Ogg voice note before anything decodes it.
        try:
            problem = await anyio.to_thread.run_sync(probe, copy)
        except Exception:
            logger.warning("voice note %s could not be checked", session_id, exc_info=True)
            problem = "unreadable"
        if problem is not None:
            logger.warning("voice note %s refused before decoding: %s", session_id, problem)
            await finish("failed", NOT_VOICE_REPLY)
            return

        try:
            wav = await anyio.to_thread.run_sync(decode_audio, copy)
            voice_row.peaks = compute_peaks(wav, n=800)

            transcript = await anyio.to_thread.run_sync(transcriber.transcribe, copy)
            voice_row.transcript = transcript.model_dump()
        except Exception:
            logger.exception("voice analysis %s failed", session_id)
            await session.rollback()
            await finish("failed", FAILED_TEXT)
            return
    finally:
        await anyio.to_thread.run_sync(remove_voice_copy, copy)

    try:
        if no_speech(transcript):
            await finish("no_speech", NO_SPEECH_TEXT)
            return

        m = compute_metrics(transcript)
        session.add(
            VoiceMetrics(
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
        )

        issues: list[GrammarIssue] = []
        if grammar is not None:
            try:
                issues = await grammar.check(transcript.text)
            except Exception:
                logger.warning("LanguageTool unavailable; analysing without grammar", exc_info=True)

        word_scores = await anyio.to_thread.run_sync(
            score_words, wav, transcript.words, phoneme_model
        )
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

        fixes = choose_fixes(m, issues, word_scores)
        fb = await phrase_feedback(completer, fixes, m)
        report = render_voice_report(voice_row.duration_s, m, issues, word_scores, fixes, fb)

        out_path: Path | None = None
        if speaker is not None:
            out_path = await anyio.to_thread.run_sync(
                speaker.speak, fb.summary, reply_path(voice_dir, voice_row.id)
            )
    except Exception:
        logger.exception("voice analysis %s failed", session_id)
        await session.rollback()
        await finish("failed", FAILED_TEXT)
        return

    await finish("analysed", None)
    if outbox is not None:
        await outbox.send_text(
            report, button={"text": KEEP_BUTTON_TEXT, "data": f"keep_voice:{voice_row.id}"}
        )
        if out_path is not None:
            await outbox.send_voice(out_path)
