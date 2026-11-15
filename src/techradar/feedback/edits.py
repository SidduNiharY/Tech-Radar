"""Track user edits to AI-generated notes and summaries, compute metrics and critique signals."""

from __future__ import annotations

import difflib
import hashlib
import re
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Edit


class EditMetrics(BaseModel):
    """Metrics comparing generated content with subsequent user edits."""

    length_change: int = Field(description="Character difference (edited - generated)")
    sections_removed: list[str] = Field(
        default_factory=list, description="Markdown ## headings removed by user"
    )
    words_replaced: int = Field(
        default=0, description="Estimated count of replaced or heavily edited words"
    )


def _extract_headings(text: str) -> list[str]:
    """Extract level-2 markdown headings."""
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE)]


def _extract_words(text: str) -> list[str]:
    """Extract tokenized words from text."""
    return re.findall(r"\b\w+\b", text)


def compare_edit(generated: str, edited: str) -> EditMetrics:
    """Compare generated note with edited note to extract diff metrics."""
    gen_headings = _extract_headings(generated)
    edited_headings = set(_extract_headings(edited))
    removed = [h for h in gen_headings if h not in edited_headings]

    length_change = len(edited) - len(generated)

    gen_words = _extract_words(generated)
    edited_words = _extract_words(edited)
    matcher = difflib.SequenceMatcher(None, gen_words, edited_words)

    words_replaced = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            words_replaced += max(i2 - i1, j2 - j1)

    return EditMetrics(
        length_change=length_change,
        sections_removed=removed,
        words_replaced=words_replaced,
    )


def diff_ratio(generated: str, edited: str) -> float:
    """Compute overall similarity ratio between generated and edited text."""
    matcher = difflib.SequenceMatcher(None, generated, edited)
    return matcher.ratio()


def generate_critique_signals(
    metrics: EditMetrics,
    original_length: int | None = None,
) -> list[str]:
    """Derive critique signals (e.g. shorten, remove_section) from edit metrics."""
    signals: list[str] = []
    for sec in metrics.sections_removed:
        signals.append(f"remove_section:{sec}")

    if original_length and original_length > 0:
        ratio = metrics.length_change / original_length
        if ratio <= -0.3:
            signals.append("shorten")
    elif metrics.length_change < -200:
        signals.append("shorten")

    if metrics.words_replaced >= 20:
        signals.append("heavy_rephrase")

    return signals


def snapshot_path(doc_path: str, base_dir: Path | None = None) -> Path:
    """Compute deterministic snapshot path from document path."""
    digest = hashlib.sha256(doc_path.encode("utf-8")).hexdigest()
    root = base_dir or Path("data/generated-snapshots")
    return root / f"{digest}.md"


def save_snapshot(
    doc_path: str,
    content: str,
    *,
    is_generated: bool = True,
    base_dir: Path | None = None,
) -> Path | None:
    """Save snapshot of generated note content if generated: true."""
    if not is_generated:
        return None
    target = snapshot_path(doc_path, base_dir=base_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def load_snapshot(doc_path: str, base_dir: Path | None = None) -> str | None:
    """Load latest generated snapshot for document if available."""
    target = snapshot_path(doc_path, base_dir=base_dir)
    if not target.exists():
        return None
    return target.read_text(encoding="utf-8")


async def record_edit(
    session: AsyncSession,
    *,
    doc_path: str,
    before: str,
    after: str,
) -> Edit:
    """Record an edit to an AI-generated note in the database."""
    metrics = compare_edit(before, after)
    before_hash = hashlib.sha256(before.encode("utf-8")).hexdigest()
    after_hash = hashlib.sha256(after.encode("utf-8")).hexdigest()

    edit_row = Edit(
        doc_path=doc_path,
        before_hash=before_hash,
        after_hash=after_hash,
        length_change=metrics.length_change,
        sections_removed=metrics.sections_removed,
        words_replaced=metrics.words_replaced,
    )
    session.add(edit_row)
    await session.flush()
    return edit_row
