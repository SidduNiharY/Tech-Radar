"""Builders for Phase 2c intake test files (generated, so no binaries in git)."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import Path

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
)
PACKAGE_RELS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>'
)
DOCUMENT = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>Hello library</w:t></w:r></w:p></w:body></w:document>"
)
XXE_DOCUMENT = (
    '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p></w:body></w:document>"
)


def make_docx(
    path: Path, *, document: str = DOCUMENT, extra: dict[str, bytes] | None = None
) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", PACKAGE_RELS)
        z.writestr("word/document.xml", document)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


def make_epub(path: Path, *, chapters: list[tuple[str, str]] | None = None) -> Path:
    chapters = chapters or [("Chapter 1", "First text."), ("Chapter 2", "Second text.")]
    manifest = "".join(
        f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
        for i in range(len(chapters))
    )
    spine = "".join(f'<itemref idref="c{i}"/>' for i in range(len(chapters)))
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f"<manifest>{manifest}</manifest><spine>{spine}</spine></package>"
    )
    container = (
        '<?xml version="1.0"?><container version="1.0" '
        'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>"
    )
    with zipfile.ZipFile(path, "w") as z:
        # EPUB rule: "mimetype" first and stored, so its bytes sit at the start.
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        for i, (title, text) in enumerate(chapters):
            xhtml = (
                '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
                f"<head><title>{title}</title></head><body><h1>{title}</h1><p>{text}</p>"
                "</body></html>"
            )
            z.writestr(f"OEBPS/c{i}.xhtml", xhtml, zipfile.ZIP_DEFLATED)
    return path


def make_zip_bomb(path: Path, *, uncompressed: int = 210_000_000) -> Path:
    """A DOCX-shaped zip whose one entry inflates past the 200 MB limit."""
    chunk = b"\0" * 1_000_000
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        with z.open("word/document.xml", "w", force_zip64=True) as f:
            for _ in range(uncompressed // len(chunk)):
                f.write(chunk)
    return path


def make_traversal_epub(path: Path) -> Path:
    make_epub(path)
    with zipfile.ZipFile(path, "a") as z:
        z.writestr("../../evil.xhtml", "<p>escape</p>")
    return path


def make_symlink_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        info = zipfile.ZipInfo("word/link.xml")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc/passwd")
    return path


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


# Media file heads (enough for signature detection; ffprobe tests build real files).
MP4_HEAD = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
MOV_HEAD = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  "
M4A_HEAD = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A mp42isom"
WEBM_HEAD = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\x82\x84webm"
MKV_HEAD = b"\x1a\x45\xdf\xa3\xa3\x42\x86\x81\x01\x42\x82\x88matroska"
MP3_HEAD = b"ID3\x04\x00\x00\x00\x00\x00\x00"
WAV_HEAD = b"RIFF\x24\x00\x00\x00WAVEfmt "
OGG_HEAD = b"OggS\x00\x02" + b"\x00" * 20
PNG_HEAD = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
JPEG_HEAD = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
HLS_PLAYLIST = b"#EXTM3U\n#EXT-X-VERSION:3\n#EXTINF:10,\nfile:///etc/passwd\n"
FFCONCAT = b"ffconcat version 1.0\nfile '/etc/passwd'\n"
