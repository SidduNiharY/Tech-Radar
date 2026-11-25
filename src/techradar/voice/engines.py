"""The real voice engines, loaded only inside the `voice-worker` container.

None of the packages are approved yet (`infra/policy/approved_deps.yaml`), so nothing here
imports them: `load_engines` says so and the analysis job tells the owner the feature is not set
up. The job body (`voice.jobs.analyse_voice`) already takes every engine as a Protocol, so
approving the packages changes this file only.

WIRING(claude): once the owner approves `faster-whisper`, `kokoro-onnx`, `transformers` and
`torch` and builds the `voice-worker` image (Phase 6 Task 2, `infra/models/voice.yaml`):
  - `FasterWhisperTranscriber(model_dir, device="cuda", compute_type="int8_float16")` with
    `word_timestamps=True`, `vad_filter=True`, `initial_prompt=FILLER_PROMPT`,
    `condition_on_previous_text=False`, building a `Transcript` (`voice.transcribe`).
  - `Wav2Vec2PhonemeModel(model_dir, device)` (`voice.pronounce.PhonemeModel`): fp16 on CUDA,
    `trust_remote_code=False`, `HF_HUB_OFFLINE=1`, safetensors only.
  - `KokoroOnnxSpeaker` already exists in `voice.speak`; give it the model and voices paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pronounce needs numpy; the worker image may not have it
    from techradar.voice.pronounce import PhonemeModel
    from techradar.voice.speak import Speaker
    from techradar.voice.transcribe import Transcriber

NOT_SET_UP_TEXT = "Voice analysis isn't set up on this server yet."


class EnginesNotApproved(RuntimeError):
    """The voice engines are not installed or approved yet."""


@dataclass(frozen=True)
class VoiceEngines:
    transcriber: Transcriber
    phoneme_model: PhonemeModel
    speaker: Speaker


def load_engines(model_dir: Path) -> VoiceEngines:
    """Load the three engines from `model_dir` (baked into the voice-worker image)."""
    raise EnginesNotApproved(
        "faster-whisper, wav2vec2 and Kokoro are not approved; see the WIRING note in "
        "techradar.voice.engines"
    )
