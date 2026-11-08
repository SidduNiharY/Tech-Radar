from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest

from techradar.library.bulk import (
    BulkDocumentManager,
    DuplicateDocumentError,
    compute_file_sha256,
    is_file_settled,
)
from techradar.library.models import Chapter, LibraryPart


def test_partial_sync_file_skipped(tmp_path: Path) -> None:
    """Verifies that files still modifying, too recent, or temp syncthing files are not settled."""
    # 1. Freshly created file has mtime ~ now, should not be settled with min_age_s=5.0
    syncing_file = tmp_path / "incoming_book.pdf"
    syncing_file.write_bytes(b"%PDF-1.5 partial file content")
    assert is_file_settled(syncing_file, min_age_s=5.0) is False

    # 2. File with mtime older than min_age_s should be settled
    old_time = time.time() - 10.0
    os.utime(syncing_file, (old_time, old_time))
    assert is_file_settled(syncing_file, min_age_s=5.0) is True

    # 3. Syncthing temporary file is skipped even if mtime is old
    tmp_syncthing = tmp_path / ".syncthing.incoming_book.pdf.tmp"
    tmp_syncthing.write_bytes(b"temp syncthing data")
    os.utime(tmp_syncthing, (old_time, old_time))
    assert is_file_settled(tmp_syncthing, min_age_s=5.0) is False

    # 4. Non-existent file is not settled
    assert is_file_settled(tmp_path / "does_not_exist.pdf") is False


def test_duplicate_book_detected(tmp_path: Path) -> None:
    """Verifies that same sha256 is detected and duplicate registration is rejected."""
    manager = BulkDocumentManager(base_dir=tmp_path / "library")

    file1 = tmp_path / "algorithms.pdf"
    content = b"%PDF-1.4 Cormen Leiserson Rivest Stein Algorithms"
    file1.write_bytes(content)

    doc1 = manager.register_document(file1, title="CLRS Algorithms", page_count=50)
    assert doc1.sha256 == compute_file_sha256(file1)
    assert doc1.title == "CLRS Algorithms"
    assert doc1.original_path.exists()

    # Permissions on original copy must be 0o440 (read-only)
    file_mode = stat.S_IMODE(doc1.original_path.stat().st_mode)
    assert file_mode == 0o440

    # Second file with different name but identical sha256 content
    file2 = tmp_path / "algorithms_copy.pdf"
    file2.write_bytes(content)

    with pytest.raises(DuplicateDocumentError):
        manager.register_document(file2, title="Duplicate Algorithms")

    # Registering the same file again must also be rejected
    with pytest.raises(DuplicateDocumentError):
        manager.register_document(file1, title="CLRS Algorithms")


def test_bulk_resumes_after_restart(tmp_path: Path) -> None:
    """Verifies that processing resumes at the next unfinished part after a server restart."""
    manager = BulkDocumentManager(base_dir=tmp_path / "library", library_part_pages=25)

    doc_file = tmp_path / "operating_systems.pdf"
    doc_file.write_bytes(b"%PDF-1.4 Silberschatz Galvin OS concepts 100 pages")

    # 100 pages with 25-page chunks = 4 parts
    doc = manager.register_document(doc_file, title="Operating Systems", page_count=100)
    assert len(doc.parts) == 4
    assert [p.part_index for p in doc.parts] == [1, 2, 3, 4]

    # Simulate parts 1 and 2 completed before crash
    doc.parts[0].status = "done"
    doc.parts[1].status = "done"
    # Part 3 was in-flight when server crashed
    doc.parts[2].status = "processing"
    # Part 4 was pending
    doc.parts[3].status = "pending"

    # Server restarts: resume_processing is called
    resumed_parts = manager.resume_processing(doc.doc_id)

    # Must only return unfinished parts (part 3 and part 4)
    assert len(resumed_parts) == 2
    assert resumed_parts[0].part_index == 3
    assert resumed_parts[0].start_page == 51
    assert resumed_parts[0].end_page == 75
    # The previously crashed 'processing' part should be reset to 'pending'
    assert resumed_parts[0].status == "pending"

    assert resumed_parts[1].part_index == 4
    assert resumed_parts[1].start_page == 76
    assert resumed_parts[1].end_page == 100
    assert resumed_parts[1].status == "pending"


def test_failed_part_noted_in_chapter(tmp_path: Path) -> None:
    """Verifies failed part records missing page numbers in chapter while chapter stays usable."""
    manager = BulkDocumentManager(base_dir=tmp_path / "library", library_part_pages=25)

    chapter = Chapter(
        title="Process Synchronization",
        ordinal=2,
        start_page=1,
        end_page=50,
        slug="process-synchronization",
    )
    assert chapter.missing_pages == []

    part1 = LibraryPart(
        book_slug="operating-systems",
        part_index=1,
        start_page=1,
        end_page=25,
        status="pending",
    )
    manager.register_part(part1)

    # Part 1 fails parsing
    updated_chapter = manager.record_part_failure(
        part_id=part1.part_id,
        chapter=chapter,
        error_msg="RapidOCR memory allocation failure",
    )

    # Missing pages 1 to 25 recorded
    assert updated_chapter.missing_pages == list(range(1, 26))
    # Chapter remains fully usable
    assert updated_chapter.title == "Process Synchronization"
    assert updated_chapter.ordinal == 2
    assert updated_chapter.start_page == 1
    assert updated_chapter.end_page == 50
    assert updated_chapter.slug == "process-synchronization"

    # Part status is updated to failed
    assert part1.status == "failed"
    assert part1.error == "RapidOCR memory allocation failure"
