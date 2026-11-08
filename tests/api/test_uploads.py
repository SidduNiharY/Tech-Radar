"""Tests for secure library file uploads (SEC-57 & Decision D48)."""

from pathlib import Path

import pytest

from techradar.api.uploads import (
    MAX_UPLOAD_SIZE_BYTES,
    SecurityError,
    sanitize_upload_filename,
    save_library_upload,
)


def test_upload_name_cannot_escape(tmp_path: Path) -> None:
    """Filenames with traversal components cannot escape the upload directory."""
    traversal_inputs = [
        "../../etc/passwd.pdf",
        "/etc/shadow.txt",
        r"..\..\system32\calc.docx",
        "../../../malicious.epub",
        "nested/../../secret.mp4",
    ]

    for raw_name in traversal_inputs:
        saved = save_library_upload(raw_name, b"test content", tmp_path)
        assert saved.exists()
        assert saved.is_file()
        # Verify the saved file is strictly within tmp_path
        assert saved.resolve().is_relative_to(tmp_path.resolve())
        assert ".." not in saved.name
        assert "/" not in saved.name
        assert "\\" not in saved.name

    # Raw traversal tokens with no valid file extension are completely rejected
    invalid_traversals = ["../../", "/etc/", r"..\..", "..", "."]
    for bad in invalid_traversals:
        with pytest.raises((ValueError, SecurityError)):
            sanitize_upload_filename(bad)
        with pytest.raises((ValueError, SecurityError)):
            save_library_upload(bad, b"test content", tmp_path)


def test_upload_valid_file_saved_with_safe_permissions(tmp_path: Path) -> None:
    """Clean files are saved with mode 0o600 inside the upload directory."""
    data = b"%PDF-1.4 test document content"
    filename = "standard_document.pdf"

    saved = save_library_upload(filename, data, tmp_path)
    assert saved.exists()
    assert saved.read_bytes() == data
    assert saved.resolve().is_relative_to(tmp_path.resolve())

    # Permissions must be 0o600 (owner read/write only)
    file_mode = saved.stat().st_mode & 0o777
    assert file_mode == 0o600


def test_upload_size_limit_enforced(tmp_path: Path) -> None:
    """Uploads exceeding 300MB must raise ValueError."""
    # Size limit is exactly 300 MB
    oversized = MAX_UPLOAD_SIZE_BYTES + 1

    # Simulate oversized data without allocating huge memory if possible, or using a slice
    # In Python, bytearray can be allocated or we can mock/check length
    class FakeOversizedBytes:
        def __len__(self) -> int:
            return oversized

    # Pass object with len > 300MB
    with pytest.raises(ValueError, match="exceeds 300MB limit"):
        save_library_upload("toolarge.pdf", FakeOversizedBytes(), tmp_path)  # type: ignore[arg-type]

    # Valid payload size under 300MB succeeds
    saved = save_library_upload("small.pdf", b"small payload", tmp_path)
    assert saved.exists()


def test_disallowed_extension_rejected(tmp_path: Path) -> None:
    """Disallowed extensions like .exe, .sh, .php must be rejected."""
    bad_extensions = [
        "virus.exe",
        "script.sh",
        "backdoor.php",
        "exploit.bat",
        "source.py",
        "archive.zip",
        "package.tar.gz",
        "noextension",
    ]

    for bad in bad_extensions:
        with pytest.raises(ValueError, match="Disallowed file extension"):
            sanitize_upload_filename(bad)

        with pytest.raises(ValueError, match="Disallowed file extension"):
            save_library_upload(bad, b"payload", tmp_path)


def test_null_bytes_and_non_printable_rejected(tmp_path: Path) -> None:
    """Null bytes and non-printable characters are rejected."""
    with pytest.raises((ValueError, SecurityError), match="Null bytes"):
        sanitize_upload_filename("test\x00file.pdf")

    with pytest.raises((ValueError, SecurityError), match="Non-printable"):
        sanitize_upload_filename("test\x07bell.pdf")
