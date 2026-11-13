"""Strict validation of media probe and segment results (untrusted sandbox output)."""

from __future__ import annotations

import math
import re
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

SEGMENT_S = 600
MAX_DURATION_S = 14_460
MAX_SLIDES_PER_SEGMENT = 40
MAX_SLIDE_TEXT = 4_000
_AUDIO_FILE = re.compile(r"^audio/seg-\d{5}\.flac$")


class MediaProbe(BaseModel):
    model_config = {"extra": "forbid"}

    duration_s: Annotated[float, Field(gt=0, le=MAX_DURATION_S, allow_inf_nan=False)]
    has_audio: bool
    has_video: bool


class Slide(BaseModel):
    model_config = {"extra": "forbid"}

    ts_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    text: Annotated[str, Field(max_length=MAX_SLIDE_TEXT)]


class SegmentResult(BaseModel):
    model_config = {"extra": "forbid"}

    audio_file: str
    slides: Annotated[list[Slide], Field(max_length=MAX_SLIDES_PER_SEGMENT)]


def segment_bounds(duration_s: float) -> list[tuple[float, float]]:
    """(ts_start, ts_end) of each 600 s segment of a media file."""
    n = math.ceil(duration_s / SEGMENT_S)
    return [(float(SEGMENT_S * i), min(float(SEGMENT_S * (i + 1)), duration_s)) for i in range(n)]


def segment_audio_name(ts_start: float) -> str:
    return f"audio/seg-{int(ts_start):05d}.flac"


def parse_probe(text: str) -> MediaProbe | None:
    try:
        return MediaProbe.model_validate_json(text)
    except ValidationError:
        return None


def parse_segment_result(text: str, ts_start: float, ts_end: float) -> SegmentResult | None:
    """The validated segment result, or None when it is not exactly the contract."""
    try:
        res = SegmentResult.model_validate_json(text)
    except ValidationError:
        return None
    if not _AUDIO_FILE.fullmatch(res.audio_file) or res.audio_file != segment_audio_name(ts_start):
        return None
    if any(not ts_start <= s.ts_s <= ts_end for s in res.slides):
        return None
    return res
