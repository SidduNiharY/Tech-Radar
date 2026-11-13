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
_XML_PART = re.compile(r"(\.xml|\.rels)$", re.IGNORECASE)


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


_EPUB_XML_PART = re.compile(r"(\.xml|\.opf|\.ncx|\.xhtml|\.html?)$", re.IGNORECASE)


def _xml_safe(path: Path, part: re.Pattern[str], *, forbid_dtd: bool) -> IntakeStep:
    try:
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if info.is_dir() or not part.search(info.filename):
                    continue
                if info.file_size > _MAX_XML_PART:
                    return _step("reject", "xml_part_too_large")
                data = z.read(info)
                try:
                    SafeET.fromstring(
                        data, forbid_dtd=forbid_dtd, forbid_entities=True, forbid_external=True
                    )
                except DefusedXmlException:
                    return _step("reject", "xml_entities")
                except SafeET.ParseError:
                    return _step("reject", "xml_invalid")
    except (zipfile.BadZipFile, OSError) as exc:
        return _step("reject", f"unreadable archive ({type(exc).__name__})")
    return _step("ok", "xml safe")


def office_xml_safe(path: Path) -> IntakeStep:
    """Reject DOCX XML parts with any DTD or entities (XXE, billion laughs)."""
    return _xml_safe(path, _XML_PART, forbid_dtd=True)


def epub_xml_safe(path: Path) -> IntakeStep:
    """Reject EPUB XML/XHTML parts with entities or external references.

    A plain DOCTYPE is allowed: EPUB 2 XHTML commonly declares one. Entity
    declarations and external references are still refused.
    """
    return _xml_safe(path, _EPUB_XML_PART, forbid_dtd=False)
