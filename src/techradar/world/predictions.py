from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import Prediction


def parse_predict(arg: str, today: date) -> tuple[str, date] | str:
    """Parse a /predict argument formatted as '<text> by <YYYY-MM-DD>'."""
    if len(arg) > 280:
        return "Keep it under 280 characters."

    parts = re.split(r"\s+by\s+", arg.strip(), flags=re.IGNORECASE)
    if len(parts) != 2:
        return "Use: /predict <your prediction> by YYYY-MM-DD"

    text = parts[0].strip()
    date_str = parts[1].strip()

    try:
        due = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Use: /predict <your prediction> by YYYY-MM-DD"

    if due <= today:
        return "Pick a future date."

    return text, due


def render_predictions_context(predictions: list[Prediction]) -> str:
    """Render active and resolved predictions for agent context."""
    lines: list[str] = [
        "---",
        "type: predictions",
        "generated: true",
        "---",
        "",
        "# Opinions and Predictions Log",
        "",
    ]
    for p in predictions:
        status = "Pending"
        if p.outcome == 1:
            status = "Right"
        elif p.outcome == 2:
            status = "Wrong"
        elif p.outcome == 3:
            status = "Partly"

        created_str = p.created_at.date().isoformat()
        due_str = p.due_date.isoformat()
        lines.append(f"- **{created_str}** (Due: {due_str} | {status}): {p.text}")
        if p.outcome_text:
            lines.append(f"  Outcome notes: {p.outcome_text}")

    return "\n".join(lines)


async def get_due_predictions(session: AsyncSession, today: date) -> list[Prediction]:
    """Retrieve all predictions due today or earlier that have not been resolved."""
    stmt = (
        select(Prediction)
        .where(Prediction.due_date <= today)
        .where(Prediction.outcome.is_(None))
        .order_by(Prediction.due_date.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def record_prediction(
    session: AsyncSession,
    text: str,
    due_date: date,
    vault_root: Path | None = None,
) -> int:
    """Save a new forecast and update context document."""
    pred = Prediction(text=text, due_date=due_date)
    session.add(pred)
    await session.flush()

    if vault_root is not None:
        await sync_predictions_vault(session, vault_root)

    await session.commit()
    return int(pred.id)


async def record_outcome(
    session: AsyncSession,
    pred_id: int,
    outcome: int,
    outcome_text: str | None = None,
    vault_root: Path | None = None,
) -> None:
    """Resolve a prediction with outcome and optional explanation."""
    stmt = select(Prediction).where(Prediction.id == pred_id)
    res = await session.execute(stmt)
    pred = res.scalar_one_or_none()
    if pred is not None:
        pred.outcome = outcome
        pred.outcome_text = outcome_text

        if vault_root is not None:
            await sync_predictions_vault(session, vault_root)

        await session.commit()


async def sync_predictions_vault(session: AsyncSession, vault_root: Path) -> None:
    """Write context/predictions.md to the Obsidian vault."""
    stmt = select(Prediction).order_by(Prediction.created_at.desc())
    res = await session.execute(stmt)
    preds = list(res.scalars().all())

    out_file = vault_root / "context" / "predictions.md"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(render_predictions_context(preds), encoding="utf-8")
