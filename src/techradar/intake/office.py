"""Office document checks (Intake Gateway step 4, Phase 2c, D34).

Both functions expect the file to have passed `check_zip` first.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from defusedxml import DefusedXmlException
from defusedxml import ElementTree as SafeET

from techradar.schemas.pipeline import IntakeStep

_MAX_XML_PART = 50_000_000


def _step(outcome: str, detail: str) -> IntakeStep:
    return IntakeStep(name="structure", outcome=outcome, detail=detail)


def check_office(path: Path) -> IntakeStep:
    """Quarantine documents with macros (D34).

    Signals, any of which quarantines: a VBA project in the archive, a
    macro-enabled content type, or oletools finding VBA. If oletools cannot
    read the file, it is quarantined too (fail closed).
    """
    try:
        with zipfile.ZipFile(path) as z:
            names = [i.filename for i in z.infolist()]
            if any(n.lower().endswith("vbaproject.bin") for n in names):
                return _step("quarantine", "macros (vbaProject.bin)")
            if "[Content_Types].xml" in names:
                info = z.getinfo("[Content_Types].xml")
                if info.file_size <= _MAX_XML_PART:
                    types = z.read(info).decode("utf-8", "replace")
                    if "macroenabled" in types.lower():
                        return _step("quarantine", "macros (macro-enabled content type)")
    except zipfile.BadZipFile, OSError, KeyError:
        return _step("quarantine", "macro scan failed: unreadable archive")

    try:
        from oletools.olevba import VBA_Parser

        parser = VBA_Parser(str(path))
        try:
            has_macros = bool(parser.detect_vba_macros())
        finally:
            parser.close()
    except Exception as exc:  # oletools raises many types on odd input
        return _step("quarantine", f"macro scan failed ({type(exc).__name__})")
    if has_macros:
        return _step("quarantine", "macros (oletools)")
    return _step("ok", "no macros")


_ENTITY = re.compile(rb"<!ENTITY", re.IGNORECASE)
_BOM_AND_SPACE = b"\xef\xbb\xbf \t\r\n"


def _looks_like_xml(data: bytes) -> bool:
    return data.lstrip(_BOM_AND_SPACE).startswith(b"<")


def _xml_safe(path: Path, *, forbid_dtd: bool) -> IntakeStep:
    """Check every entry, whatever its name.

    Parts are chosen by their declared content type, not their name, so any
    entry can be XML. An entity declaration anywhere is refused, and every
    entry whose content starts like XML is parsed with defusedxml.
    """
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                if info.file_size > _MAX_XML_PART:
                    with z.open(info) as fh:
                        if _looks_like_xml(fh.read(1024)):
                            return _step("reject", "xml_part_too_large")
                    continue
                data = z.read(info)
                if _ENTITY.search(data):
                    return _step("reject", "xml_entities")
                if not _looks_like_xml(data):
                    continue
                try:
                    SafeET.fromstring(
                        data, forbid_dtd=forbid_dtd, forbid_entities=True, forbid_external=True
                    )
                except DefusedXmlException:
                    return _step("reject", "xml_entities")
                except SafeET.ParseError:
                    return _step("reject", f"xml_invalid: {info.filename[:80]!r}")
    except (zipfile.BadZipFile, OSError) as exc:
        return _step("reject", f"unreadable archive ({type(exc).__name__})")
    return _step("ok", "xml safe")


def office_xml_safe(path: Path) -> IntakeStep:
    """Reject DOCX XML parts with any DTD or entities (XXE, billion laughs)."""
    return _xml_safe(path, forbid_dtd=True)


def epub_xml_safe(path: Path) -> IntakeStep:
    """Reject EPUB XML/XHTML parts with entities or external references.

    A plain DOCTYPE is allowed: EPUB 2 XHTML commonly declares one. Entity
    declarations and external references are still refused.
    """
    return _xml_safe(path, forbid_dtd=False)
