from __future__ import annotations

import re

from techradar.schemas.pipeline import IntakeStep

PDF_QUARANTINE: tuple[str, ...] = (
    "/JavaScript",
    "/JS",
    "/Launch",
    "/EmbeddedFile",
    "/RichMedia",
    "/XFA",
)

PDF_FLAG: tuple[str, ...] = (
    "/OpenAction",
    "/AA",
)


def pdf_keywords(data: bytes) -> dict[str, int]:
    """Extract and count PDF name tokens after resolving #xx hex escapes."""
    # Decode #xx hex escapes in PDF names
    decoded = re.sub(
        rb"#([0-9a-fA-F]{2})",
        lambda m: bytes([int(m.group(1), 16)]),
        data,
    )

    counts: dict[str, int] = {}
    for token in PDF_QUARANTINE + PDF_FLAG:
        token_bytes = token.encode("ascii")
        # Match token as distinct name boundary
        pattern = re.escape(token_bytes) + rb"(?=[^a-zA-Z0-9_-]|$)"
        matches = len(re.findall(pattern, decoded))
        if matches > 0:
            counts[token] = matches
    return counts


def check_pdf(data: bytes) -> IntakeStep:
    """Inspect PDF structure tokens for dangerous executable or autorun elements."""
    kw = pdf_keywords(data)

    quarantined = [k for k in PDF_QUARANTINE if kw.get(k, 0) > 0]
    if quarantined:
        return IntakeStep(
            name="structure",
            outcome="quarantine",
            detail=f"dangerous keywords: {', '.join(quarantined)}",
        )

    flagged = [k for k in PDF_FLAG if kw.get(k, 0) > 0]
    if flagged:
        return IntakeStep(
            name="structure",
            outcome="flag",
            detail=f"suspicious keywords: {', '.join(flagged)}",
        )

    return IntakeStep(name="structure", outcome="ok", detail="clean structure")
