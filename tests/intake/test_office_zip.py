"""Phase 2c Task 3: archive, Office macro and Office XML checks."""

import zipfile

from techradar.intake.office import check_office, epub_xml_safe, office_xml_safe
from techradar.intake.zipcheck import check_zip

from .library_fixtures import (
    XXE_DOCUMENT,
    make_docx,
    make_epub,
    make_symlink_zip,
    make_traversal_epub,
    make_zip_bomb,
)


def test_ok_docx_and_epub_pass(tmp_path):
    assert check_zip(make_docx(tmp_path / "a.docx")).outcome == "ok"
    assert check_zip(make_epub(tmp_path / "b.epub")).outcome == "ok"


def test_zip_bomb_rejected(tmp_path):
    step = check_zip(make_zip_bomb(tmp_path / "bomb.docx"))
    assert step.outcome == "reject" and step.name == "structure"


def test_high_ratio_entry_rejected_even_under_the_total(tmp_path):
    p = tmp_path / "r.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("word/document.xml", b"\0" * 5_000_000)  # ratio about 1000:1
    assert check_zip(p).outcome == "reject"


def test_too_many_entries_rejected(tmp_path):
    p = tmp_path / "many.epub"
    with zipfile.ZipFile(p, "w") as z:
        for i in range(30):
            z.writestr(f"x/{i}.txt", b"a")
    assert check_zip(p, max_entries=20).outcome == "reject"


def test_epub_path_traversal_rejected(tmp_path):
    assert check_zip(make_traversal_epub(tmp_path / "t.epub")).outcome == "reject"


def test_absolute_name_rejected(tmp_path):
    p = tmp_path / "abs.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("/etc/cron.d/x", b"x")
    assert check_zip(p).outcome == "reject"


def test_symlink_entry_rejected(tmp_path):
    assert check_zip(make_symlink_zip(tmp_path / "s.docx")).outcome == "reject"


def test_encrypted_entry_rejected(tmp_path):
    # Encrypted entries cannot be inspected, so they cannot be trusted.
    p = make_docx(tmp_path / "e.docx")
    data = bytearray(p.read_bytes())
    # Set flag bit 0 ("encrypted") in every local header (flags at +6) and
    # central directory header (flags at +8); zipfile's writer clears it.
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        i = data.find(sig)
        while i != -1:
            data[i + off] |= 0x1
            i = data.find(sig, i + 4)
    p.write_bytes(bytes(data))
    assert check_zip(p).outcome == "reject"


def test_not_a_zip_rejected(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"PK\x03\x04garbage")
    assert check_zip(p).outcome == "reject"


def test_macro_docx_quarantined(tmp_path):
    # A .docm renamed to .docx: the VBA project travels in vbaProject.bin.
    p = make_docx(tmp_path / "m.docx", extra={"word/vbaProject.bin": b"\xd0\xcf\x11\xe0fake"})
    step = check_office(p)
    assert step.outcome == "quarantine" and step.name == "structure"


def test_macro_enabled_content_type_quarantined(tmp_path):
    p = tmp_path / "m2.docx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types><Override PartName="/word/document.xml" ContentType="application/'
            'vnd.ms-word.document.macroEnabled.main+xml"/></Types>',
        )
        z.writestr("word/document.xml", "<w:document/>")
    assert check_office(p).outcome == "quarantine"


def test_clean_docx_has_no_macros(tmp_path):
    assert check_office(make_docx(tmp_path / "ok.docx")).outcome == "ok"


def test_xxe_docx_rejected(tmp_path):
    step = office_xml_safe(make_docx(tmp_path / "x.docx", document=XXE_DOCUMENT))
    assert step.outcome == "reject" and step.detail == "xml_entities"


def test_clean_docx_xml_is_safe(tmp_path):
    assert office_xml_safe(make_docx(tmp_path / "ok.docx")).outcome == "ok"


def test_xml_part_with_any_name_is_checked(tmp_path):
    # Parts are chosen by declared content type, not by name, so a renamed
    # XML part with an entity must still be refused (automated review).
    p = make_docx(tmp_path / "r.docx", extra={"word/custom.dat": XXE_DOCUMENT.encode()})
    assert office_xml_safe(p).outcome == "reject"


def test_epub_part_with_any_name_is_checked(tmp_path):
    p = make_epub(tmp_path / "r.epub")
    with zipfile.ZipFile(p, "a") as z:
        z.writestr(
            "OEBPS/notes.bin",
            '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>',
        )
    assert epub_xml_safe(p).outcome == "reject"


def test_binary_entries_are_not_parsed_as_xml(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 200
    p = make_docx(tmp_path / "img.docx", extra={"word/media/image1.png": png})
    assert office_xml_safe(p).outcome == "ok"
