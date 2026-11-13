"""EPUB reader for the parser sandbox (Phase 2c Task 3).

Runs after the gateway's archive and XML checks, and checks the archive
again itself. The book's contents list is read with defusedxml; chapters
follow the spine; a manifest entry that points outside the book is skipped.
"""

from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote

from defusedxml import ElementTree as SafeET
from pydantic import BaseModel, field_validator

from techradar.intake.zipcheck import check_zip
from techradar.parser.html import html_to_doc
from techradar.security.text import sanitize_text

_XHTML_TYPES = {"application/xhtml+xml", "text/html"}
_BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "br", "tr", "blockquote"}


class EpubChapter(BaseModel):
    title: str
    text: str

    @field_validator("title")
    @classmethod
    def _cap_title(cls, v: str) -> str:
        return v[:300]


def _local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1].lower()


def _parse_xml(data: bytes):  # type: ignore[no-untyped-def]
    # EPUB 2 XHTML may carry a plain DOCTYPE; entities and external refs are refused.
    return SafeET.fromstring(data, forbid_dtd=False, forbid_entities=True, forbid_external=True)


def _xhtml_chapter(data: bytes, url: str, max_chars: int) -> tuple[str, str]:
    """(title, text) from an XHTML part; falls back to html_to_doc if not XML."""
    try:
        root = _parse_xml(data)
    except SafeET.ParseError:
        doc = html_to_doc(data, url, max_chars)
        return (doc.title if doc else ""), (doc.text if doc else "")
    title = ""
    lines: list[str] = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "title" and not title:
            title = "".join(el.itertext())
        if name in _BLOCKS:
            text = " ".join("".join(el.itertext()).split())
            if text and (not lines or lines[-1] != text):
                lines.append(text)
            if name in ("h1", "h2") and not title:
                title = text
    return sanitize_text(title), sanitize_text("\n\n".join(lines))[:max_chars]


def epub_to_chapters(path: Path, max_chars: int) -> list[EpubChapter]:
    """Chapters in spine order. Raises ValueError for an unsafe or broken book."""
    step = check_zip(path)
    if step.outcome != "ok":
        raise ValueError(f"unsafe archive: {step.detail}")
    chapters: list[EpubChapter] = []
    used = 0
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            container = _parse_xml(z.read("META-INF/container.xml"))
            rootfile = next(
                (el.get("full-path") for el in container.iter() if _local(el.tag) == "rootfile"),
                None,
            )
            if not rootfile or rootfile not in names:
                raise ValueError("epub has no package document")
            opf = _parse_xml(z.read(rootfile))
            base = posixpath.dirname(rootfile)
            manifest = {
                el.get("id"): el.get("href", "")
                for el in opf.iter()
                if _local(el.tag) == "item" and el.get("media-type") in _XHTML_TYPES
            }
            spine = [el.get("idref") for el in opf.iter() if _local(el.tag) == "itemref"]
            for idref in spine:
                href = manifest.get(idref)
                if not href:
                    continue
                target = posixpath.normpath(posixpath.join(base, unquote(href.split("#")[0])))
                if target.startswith(("../", "/")) or target == ".." or target not in names:
                    continue  # never follow a path that leaves the book
                title, text = _xhtml_chapter(z.read(target), f"epub:{target}", max_chars)
                if not text:
                    continue
                text = text[: max(0, max_chars - used)]
                if not text:
                    break
                used += len(text)
                chapters.append(
                    EpubChapter(title=title or f"Chapter {len(chapters) + 1}", text=text)
                )
    except (zipfile.BadZipFile, KeyError, SafeET.ParseError) as exc:
        raise ValueError(f"unreadable epub ({type(exc).__name__})") from exc
    return chapters
