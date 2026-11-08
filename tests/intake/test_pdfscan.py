from pathlib import Path

from techradar.intake.pdfscan import check_pdf, pdf_keywords

FIX_DIR = Path(__file__).parent / "fixtures"


def test_pdf_with_javascript_quarantined():
    data = (FIX_DIR / "pdf_with_js.pdf").read_bytes()
    assert check_pdf(data).outcome == "quarantine"


def test_pdf_hex_escaped_javascript_detected():
    assert pdf_keywords(b"<< /J#61vaScript (app.alert(1)) >>")["/JavaScript"] == 1


def test_pdf_openaction_only_flagged():
    data = (FIX_DIR / "pdf_openaction.pdf").read_bytes()
    assert check_pdf(data).outcome == "flag"
