from __future__ import annotations

from pathlib import Path

import pytest

from techradar.library.media import (
    MAX_AUDIO_SIZE_BYTES,
    MAX_VIDEO_DURATION_S,
    MAX_VIDEO_SIZE_BYTES,
    MediaLimitExceededError,
    MediaSecurityError,
    build_ffmpeg_audio_extract_args,
    build_ffmpeg_frame_extract_args,
    validate_media_limits,
)


def test_ffmpeg_args_include_protocol_whitelist(tmp_path: Path) -> None:
    """Verifies that ffmpeg extraction argument lists include -protocol_whitelist file."""
    video_file = tmp_path / "lecture.mp4"
    video_file.write_bytes(b"\x00\x00\x00 ftypisom dummy mp4")

    out_audio = tmp_path / "lecture.flac"
    audio_args = build_ffmpeg_audio_extract_args(video_file, out_audio)

    # Argument list validation (never a shell string)
    assert isinstance(audio_args, list)
    assert "-protocol_whitelist" in audio_args
    whitelist_idx = audio_args.index("-protocol_whitelist")
    assert audio_args[whitelist_idx + 1] == "file"
    assert str(video_file) in audio_args
    assert str(out_audio) in audio_args

    # Frame extract args
    out_dir = tmp_path / "frames"
    frame_args = build_ffmpeg_frame_extract_args(video_file, out_dir, fps=1 / 60.0)

    assert isinstance(frame_args, list)
    assert "-protocol_whitelist" in frame_args
    frame_wl_idx = frame_args.index("-protocol_whitelist")
    assert frame_args[frame_wl_idx + 1] == "file"
    assert str(video_file) in frame_args


@pytest.mark.parametrize(
    "playlist_name",
    [
        "stream.m3u8",
        "stream.m3u",
        "radio.pls",
        "media.asx",
        "tracks.cue",
        "list.concat",
        "list.ffconcat",
    ],
)
def test_playlists_and_concat_rejected(tmp_path: Path, playlist_name: str) -> None:
    """Verifies that playlists and concat files are rejected under SEC-44."""
    bad_file = tmp_path / playlist_name
    bad_file.write_text("dummy playlist content")

    with pytest.raises((MediaSecurityError, ValueError)):
        build_ffmpeg_audio_extract_args(bad_file, tmp_path / "out.flac")

    with pytest.raises((MediaSecurityError, ValueError)):
        build_ffmpeg_frame_extract_args(bad_file, tmp_path / "frames")


def test_concat_content_rejected(tmp_path: Path) -> None:
    """Verifies that files with ffconcat headers are rejected even if named .mp4."""
    concat_disguised = tmp_path / "disguised.mp4"
    concat_disguised.write_bytes(b"ffconcat version 1.0\nfile http://attacker.com/part1.mp4")

    with pytest.raises((MediaSecurityError, ValueError)):
        build_ffmpeg_audio_extract_args(concat_disguised, tmp_path / "out.flac")


@pytest.mark.parametrize(
    "remote_url",
    [
        "http://example.com/video.mp4",
        "https://evil.com/stream.m3u8",
        "rtmp://live.stream/video",
        "rtmps://secure.live.stream/video",
        "rtsp://cam.local/feed",
        "ftp://files.org/vid.mp4",
        "tcp://10.0.0.1:8080/stream",
    ],
)
def test_remote_urls_rejected(tmp_path: Path, remote_url: str) -> None:
    """Verifies that network URLs are rejected under SEC-44."""
    with pytest.raises((MediaSecurityError, ValueError)):
        build_ffmpeg_audio_extract_args(remote_url, tmp_path / "out.flac")

    with pytest.raises((MediaSecurityError, ValueError)):
        build_ffmpeg_frame_extract_args(remote_url, tmp_path / "frames")


def test_duration_limits_enforced() -> None:
    """Verifies video duration limit <= 14,400s (4 hours) is enforced."""
    # Under limit should pass
    validate_media_limits(duration_s=7200.0)
    validate_media_limits(duration_s=float(MAX_VIDEO_DURATION_S))

    # Over 4 hours should raise MediaLimitExceededError
    with pytest.raises(MediaLimitExceededError):
        validate_media_limits(duration_s=float(MAX_VIDEO_DURATION_S + 1))

    with pytest.raises(MediaLimitExceededError):
        validate_media_limits(duration_s=20_000.0)


def test_video_and_audio_size_limits_enforced() -> None:
    """Verifies video size <= 4GB and audio size <= 1GB limits are enforced."""
    # Video <= 4GB passes
    validate_media_limits(file_size=MAX_VIDEO_SIZE_BYTES, is_audio=False)
    # Video > 4GB fails
    with pytest.raises(MediaLimitExceededError):
        validate_media_limits(file_size=MAX_VIDEO_SIZE_BYTES + 1, is_audio=False)

    # Audio <= 1GB passes
    validate_media_limits(file_size=MAX_AUDIO_SIZE_BYTES, is_audio=True)
    # Audio > 1GB fails
    with pytest.raises(MediaLimitExceededError):
        validate_media_limits(file_size=MAX_AUDIO_SIZE_BYTES + 1, is_audio=True)
