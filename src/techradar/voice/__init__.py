"""Voice Coach (Phase 6).

The names below load lazily (PEP 562): the bot imports `techradar.voice.intake`, and the bot
image has no numpy, so importing this package must not import the analysis modules.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS: dict[str, str] = {
    "compute_peaks": "techradar.voice.audio",
    "decode_audio": "techradar.voice.audio",
    "Fix": "techradar.voice.feedback",
    "VoiceFeedback": "techradar.voice.feedback",
    "choose_fixes": "techradar.voice.feedback",
    "phrase_feedback": "techradar.voice.feedback",
    "render_voice_report": "techradar.voice.feedback",
    "check_voice_bytes": "techradar.voice.intake",
    "check_voice_limits": "techradar.voice.intake",
    "intake_voice": "techradar.voice.intake",
    "FILLERS": "techradar.voice.metrics",
    "SpeechMetrics": "techradar.voice.metrics",
    "compute_metrics": "techradar.voice.metrics",
    "FLAG_THRESHOLD": "techradar.voice.pronounce",
    "FRAME_S": "techradar.voice.pronounce",
    "PhonemeModel": "techradar.voice.pronounce",
    "WordScore": "techradar.voice.pronounce",
    "score_words": "techradar.voice.pronounce",
    "FILLER_PROMPT": "techradar.voice.transcribe",
    "Transcriber": "techradar.voice.transcribe",
    "Transcript": "techradar.voice.transcribe",
    "Word": "techradar.voice.transcribe",
    "no_speech": "techradar.voice.transcribe",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module), name)
