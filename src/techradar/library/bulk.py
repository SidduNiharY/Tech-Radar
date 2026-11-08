from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from techradar.library.models import Chapter, LibraryDoc, LibraryPart
from techradar.library.toc import chunk_by_page_ranges
from techradar.pipeline.writer import slugify


class DuplicateDocumentError(Exception):
    """Raised when registering a document that is already registered."""


def is_file_settled(path: Path | str, min_age_s: float = 5.0) -> bool:
    """Checks if a file delivered by Syncthing into library-inbox has settled.

    A file has settled when:
    - It exists and is a regular file.
    - It is not a Syncthing temporary sync file (.syncthing.* or *.tmp).
    - Its mtime is older than min_age_s (size and writes are stable over time).
    - It is not actively being written or locked (can be opened and read).
    """
    p = Path(path)
    try:
        if not p.is_file():
            return False
    except OSError:
        return False

    name = p.name
    if name.startswith(".syncthing.") or name.endswith(".tmp") or name.startswith(".~"):
        return False

    try:
        st = p.stat()
    except OSError:
        return False

    now = time.time()
    age = now - st.st_mtime
    if age < min_age_s:
        return False

    try:
        with open(p, "rb") as f:
            f.read(1)
    except OSError, PermissionError:
        return False

    return True


def compute_file_sha256(path: Path | str) -> str:
    """Computes SHA-256 digest of a file in 64KB chunks."""
    p = Path(path)
    hasher = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(64 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _get_pdf_page_count(path: Path) -> int:
    """Reads PDF page count using pypdfium2, or returns 0 if unreadable."""
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        count = len(pdf)
        pdf.close()
        return count
    except Exception:
        return 0


class BulkDocumentManager:
    """Manages document registration, deduplication, splitting, and resuming."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        library_part_pages: int = 25,
    ) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("data/library")
        self.originals_dir = self.base_dir / "originals"
        self.library_part_pages = library_part_pages
        self._docs: dict[str, LibraryDoc] = {}
        self._docs_by_hash: dict[str, LibraryDoc] = {}
        self._docs_by_slug: dict[str, LibraryDoc] = {}
        self._parts: dict[str, LibraryPart] = {}

    def register_part(self, part: LibraryPart) -> None:
        """Registers a part directly in the manager."""
        pid = part.part_id or f"{part.book_slug}-part-{part.part_index}"
        self._parts[pid] = part

    def get_document(self, doc_id: str) -> LibraryDoc | None:
        """Retrieves a document by doc_id, sha256 hash, or book slug."""
        if doc_id in self._docs:
            return self._docs[doc_id]
        if doc_id in self._docs_by_hash:
            return self._docs_by_hash[doc_id]
        if doc_id in self._docs_by_slug:
            return self._docs_by_slug[doc_id]
        return None

    def register_document(
        self,
        path: Path | str,
        title: str | None = None,
        trust: str = "official",
        page_count: int | None = None,
        require_settled: bool = False,
        min_age_s: float = 5.0,
    ) -> LibraryDoc:
        """Registers a document, checks duplicates, moves/copies file, and splits PDF parts."""
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Document file not found: {p}")

        if require_settled and not is_file_settled(p, min_age_s=min_age_s):
            raise ValueError(f"File {p} has not settled yet")

        sha256 = compute_file_sha256(p)
        if sha256 in self._docs_by_hash:
            raise DuplicateDocumentError(f"Document with sha256={sha256} already registered")

        ext = p.suffix
        dest_path = self.originals_dir / f"{sha256}{ext}"
        if dest_path.exists():
            raise DuplicateDocumentError(f"Original document file already exists at {dest_path}")

        self.originals_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest_path)
        dest_path.chmod(0o440)

        doc_title = title or p.stem
        slug = slugify(doc_title)
        if not slug or slug == "note":
            slug = f"doc-{sha256[:8]}"
        doc_id = sha256

        if page_count is None and ext.lower() == ".pdf":
            page_count = _get_pdf_page_count(dest_path)
        resolved_pages = page_count or 0

        parts: list[LibraryPart] = []
        if ext.lower() == ".pdf" and resolved_pages > 0:
            ranges = chunk_by_page_ranges(resolved_pages, part_size=self.library_part_pages)
            for idx, (sp, ep) in enumerate(ranges, start=1):
                part = LibraryPart(
                    book_slug=slug,
                    part_index=idx,
                    start_page=sp,
                    end_page=ep,
                    status="pending",
                )
                parts.append(part)
                self.register_part(part)

        doc = LibraryDoc(
            doc_id=doc_id,
            sha256=sha256,
            title=doc_title,
            original_path=dest_path,
            trust=trust,
            status="pending",
            page_count=resolved_pages,
            parts=parts,
        )
        self._docs[doc_id] = doc
        self._docs_by_hash[sha256] = doc
        self._docs_by_slug[slug] = doc
        return doc

    def resume_processing(self, doc_id: str) -> list[LibraryPart]:
        """Resumes processing from the first unfinished part after a server restart.

        Already completed ('done') parts are not reprocessed. Any parts left in
        'processing' state before restart are reset to 'pending' to be picked up again.
        """
        doc = self.get_document(doc_id)
        if not doc:
            raise KeyError(f"Document {doc_id} not found")

        unfinished_parts: list[LibraryPart] = []
        for part in doc.parts:
            if part.status == "done":
                continue
            if part.status == "processing":
                part.status = "pending"
            unfinished_parts.append(part)
        return unfinished_parts

    def record_part_failure(
        self,
        part_id: str | LibraryPart,
        chapter: Chapter,
        error_msg: str,
    ) -> Chapter:
        """Marks part as failed and records missing pages rather than dropping whole doc."""
        if isinstance(part_id, LibraryPart):
            part = part_id
            pid = part.part_id or f"{part.book_slug}-part-{part.part_index}"
            self._parts[pid] = part
        else:
            pid = part_id
            part = self._parts.get(pid)
            if not part:
                for doc in self._docs.values():
                    for p in doc.parts:
                        if p.part_id == pid or f"{p.book_slug}-part-{p.part_index}" == pid:
                            part = p
                            break
                    if part:
                        break

        if not part:
            raise KeyError(f"Part '{pid}' not found")

        part.status = "failed"
        part.error = error_msg

        part_pages = range(part.start_page, part.end_page + 1)
        overlapping_pages = [p for p in part_pages if chapter.start_page <= p <= chapter.end_page]
        if overlapping_pages:
            existing = set(chapter.missing_pages or [])
            chapter.missing_pages = sorted(existing.union(overlapping_pages))

        return chapter
