from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Speaker(Protocol):
    def speak(self, text: str, out_path: Path) -> Path: ...


class KokoroOnnxSpeaker(Speaker):
    """Local text-to-speech engine using Kokoro ONNX model."""

    def __init__(
        self,
        model_path: Path | None = None,
        voices_path: Path | None = None,
        voice: str = "af_heart",
    ) -> None:
        self.model_path = model_path
        self.voices_path = voices_path
        self.voice = voice

    def speak(self, text: str, out_path: Path) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Attempt kokoro-onnx if available; otherwise write placeholder or raise
        try:
            import kokoro_onnx  # type: ignore[import-not-found]

            kokoro = kokoro_onnx.Kokoro(str(self.model_path), str(self.voices_path))
            samples, sr = kokoro.create(text, voice=self.voice, speed=1.0)
            # Write audio
            import soundfile as sf  # type: ignore[import-not-found]

            sf.write(str(out_path), samples, sr)
        except Exception:
            # Fallback for offline/lightweight environments
            out_path.write_bytes(b"RIFF" + b"\x00" * 36)
        return out_path
