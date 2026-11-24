"""Ask a question, poll for its answer, save it to the vault.

`POST /v1/ask` stores a `pending` answers row and queues the worker's `ask` job with that
row's id; the worker fills the row in (worker/ask_flow.run_web_ask). The API runs no model.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from techradar.api.deps import AppSession, AppSettings, DbId, DeferJob, RoSession
from techradar.api.schemas import Answer, AnswerStatus, AskRequest, AskResponse, CitationOut
from techradar.db.models import Answer as AnswerRow
from techradar.worker.names import ASK, SAVE_ANSWER

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ask"])

PENDING = "pending"
FINISHED = frozenset({"answered", "not_found", "needs_review"})
MAX_CITATIONS = 20


def citations_out(raw: Any) -> list[CitationOut]:
    out: list[CitationOut] = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        try:
            out.append(CitationOut.model_validate({k: c.get(k) for k in CitationOut.model_fields}))
        except ValidationError:
            continue
        if len(out) >= MAX_CITATIONS:
            break
    return out


def answer_status(row: AnswerRow) -> AnswerStatus:
    """A pending row has no answer yet; an unknown status is shown as needing review."""
    if row.status == PENDING:
        return AnswerStatus(status="pending")
    shown = row.status if row.status in FINISHED else "needs_review"
    answer = Answer(
        id=row.id,
        question=row.question,
        text=row.text,
        citations=citations_out(row.citations),
        status=shown,  # type: ignore[arg-type]
        used_unverified=bool(row.used_unverified),
        created_at=row.created_at,
    )
    return AnswerStatus(status=shown, answer=answer)  # type: ignore[arg-type]


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest, session: AppSession, defer: DeferJob, settings: AppSettings
) -> AskResponse:
    row = AnswerRow(
        chat_id=settings.telegram_owner_chat_id,
        question=body.question,
        text="",
        status=PENDING,
    )
    session.add(row)
    await session.commit()  # the job must find the row
    args: dict[str, Any] = {"question": body.question, "answer_id": row.id}
    if body.verified_only:
        args["verified_only"] = True
    try:
        await defer(ASK, args)
    except Exception:
        logger.exception("could not queue the ask job")
        await session.delete(row)
        await session.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable") from None
    return AskResponse(answer_id=row.id)


@router.get("/answers/{answer_id}", response_model=AnswerStatus)
async def get_answer(answer_id: DbId, session: RoSession) -> AnswerStatus:
    row = await session.get(AnswerRow, answer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return answer_status(row)


@router.post("/answers/{answer_id}/save", status_code=status.HTTP_202_ACCEPTED)
async def save_answer(answer_id: DbId, session: RoSession, defer: DeferJob) -> dict[str, bool]:
    """Queue `save_answer` for an answered question; saved once (a second press is a no-op)."""
    row = await session.get(AnswerRow, answer_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if row.status != "answered":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an answered question can be saved")
    if row.saved_path is not None:
        return {"queued": False}
    await defer(SAVE_ANSWER, {"answer_id": row.id})
    return {"queued": True}
