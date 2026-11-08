from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from techradar.schemas.pipeline import IntakeStep

try:
    import yara  # type: ignore

    _HAVE_YARA = True
except ImportError:
    _HAVE_YARA = False


def load_rules(rules_dir: Path) -> Any:
    """Compile YARA rules from directory or return file paths."""
    if not rules_dir.exists():
        return None

    rule_files = list(rules_dir.glob("*.yar"))
    if not rule_files:
        return None

    if _HAVE_YARA:
        filepaths = {f.stem: str(f) for f in rule_files}
        try:
            return yara.compile(filepaths=filepaths)
        except Exception:
            return None
    return rule_files


def check_rules(rules: Any, data: bytes) -> IntakeStep:
    """Evaluate YARA rules or fallback signature matching on payload."""
    matches: list[str] = []

    if _HAVE_YARA and rules is not None and hasattr(rules, "match"):
        with contextlib.suppress(Exception):
            res = rules.match(data=data)
            matches = [m.rule for m in res]
    else:
        # Fallback signatures matching starter rules
        if b"/JavaScript" in data and b"/OpenAction" in data:
            matches.append("pdf_js_openaction")
        if data.startswith(b"MZ") and b"This program cannot be run in DOS mode" in data:
            matches.append("embedded_pe")

    if matches:
        return IntakeStep(
            name="rules",
            outcome="quarantine",
            detail=f"matched YARA rules: {', '.join(matches)}",
        )

    return IntakeStep(name="rules", outcome="ok", detail="no rule matches")
