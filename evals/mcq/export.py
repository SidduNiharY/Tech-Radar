"""Export active MCQs to Markdown checklist for human evaluation.

Writes up to 50 active MCQs to evals/mcq/review-<date>.md as a review checklist.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.engine import make_session_factory
from techradar.db.models import MCQ


def render_review_markdown(mcqs: Sequence[MCQ], review_date: date) -> str:
    """Render a checklist markdown document for human review of MCQs."""
    lines = [
        f"# MCQ Review Checklist - {review_date.isoformat()}",
        "",
        f"Total questions for review: {len(mcqs)}",
        "",
    ]
    for i, mcq in enumerate(mcqs, 1):
        source_type = "Fact" if mcq.fact_id is not None else "Chapter Chunk"
        source_id = mcq.fact_id if mcq.fact_id is not None else mcq.chunk_id
        lines.append(f"## {i}. MCQ #{mcq.id} ({source_type} #{source_id})")
        lines.append("")
        lines.append(f"**Question:** {mcq.question}")
        lines.append("")
        lines.append("**Options:**")
        for idx, opt in enumerate(mcq.options):
            marker = " (Key)" if idx == mcq.answer_index else ""
            letter = chr(ord("A") + idx)
            lines.append(f"- [ ] **{letter}.** {opt}{marker}")
        lines.append("")
        lines.append(f"**Explanation:** {mcq.explanation}")
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _write_file_sync(output_path: Path, content: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


async def export_mcqs(
    session: AsyncSession,
    output_path: Path,
    review_date: date,
    *,
    limit: int = 50,
) -> int:
    """Fetch random active MCQs from database and write to markdown checklist."""
    stmt = select(MCQ).where(MCQ.status == "active").order_by(func.random()).limit(limit)
    result = await session.execute(stmt)
    mcqs = list(result.scalars().all())

    md_content = render_review_markdown(mcqs, review_date)
    await asyncio.to_thread(_write_file_sync, output_path, md_content)
    return len(mcqs)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export active MCQs for human review.")
    parser.add_argument(
        "--date",
        type=str,
        default=date.today().isoformat(),
        help="Date for the review file (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of active MCQs to export (default 50)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Directory to save review file",
    )
    args = parser.parse_args()

    review_d = date.fromisoformat(args.date)
    out_file = args.output_dir / f"review-{review_d.isoformat()}.md"

    session_factory = make_session_factory("ro")
    async with session_factory() as session:
        count = await export_mcqs(session, out_file, review_d, limit=args.limit)
        print(f"Exported {count} active MCQs to {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
