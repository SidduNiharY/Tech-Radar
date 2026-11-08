from __future__ import annotations

from techradar.library.bulk import (
    BulkDocumentManager,
    DuplicateDocumentError,
    compute_file_sha256,
    is_file_settled,
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
from techradar.library.toc import chunk_by_page_ranges, extract_outline_chapters

__all__ = [
    "MAX_AUDIO_SIZE_BYTES",
    "MAX_VIDEO_DURATION_S",
    "MAX_VIDEO_SIZE_BYTES",
    "BookMeta",
    "BulkDocumentManager",
    "Chapter",
    "DuplicateDocumentError",
    "LibraryDoc",
    "LibraryPart",
    "MediaInfo",
    "MediaLimitExceededError",
    "MediaSecurityError",
    "build_ffmpeg_audio_extract_args",
    "build_ffmpeg_frame_extract_args",
    "check_media_limits",
    "chunk_by_page_ranges",
    "compute_file_sha256",
    "extract_outline_chapters",
    "is_file_settled",
    "probe_media",
    "validate_media_limits",
]
