from __future__ import annotations

from techradar.library.inbox import (
    MIME_TO_KIND,
    InboxFile,
    IntakeDecision,
    LibraryKind,
    classify,
    plan_library_intake,
    stable_files,
)
from techradar.library.media import (
    MAX_AUDIO_SIZE_BYTES,
    MAX_VIDEO_DURATION_S,
    MAX_VIDEO_SIZE_BYTES,
    MediaLimitExceededError,
    MediaSecurityError,
    build_ffmpeg_audio_extract_args,
    build_ffmpeg_frame_extract_args,
    check_media_limits,
    probe_media,
    validate_media_limits,
)
from techradar.library.models import BookMeta, Chapter, LibraryDoc, LibraryPart, MediaInfo
from techradar.library.starter_packs import StarterPackItem, StarterPackManager
from techradar.library.summarizer import (
    ChapterSummary,
    render_chapter_vault_note,
)

__all__ = [
    "MIME_TO_KIND",
    "InboxFile",
    "IntakeDecision",
    "LibraryKind",
    "classify",
    "plan_library_intake",
    "stable_files",
    "MAX_AUDIO_SIZE_BYTES",
    "MAX_VIDEO_DURATION_S",
    "MAX_VIDEO_SIZE_BYTES",
    "BookMeta",
    "Chapter",
    "ChapterSummary",
    "LibraryDoc",
    "LibraryPart",
    "MediaInfo",
    "MediaLimitExceededError",
    "MediaSecurityError",
    "StarterPackItem",
    "StarterPackManager",
    "build_ffmpeg_audio_extract_args",
    "build_ffmpeg_frame_extract_args",
    "check_media_limits",
    "probe_media",
    "render_chapter_vault_note",
    "validate_media_limits",
]
