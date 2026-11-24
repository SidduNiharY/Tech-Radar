"""`POST /v1/tickets/confirm` (Phase 4 Task 2b). SEC-56.

The body holds only the token; the header `X-TR-Session` names the browser tab. What runs is
the action stored with the ticket, once, in the same transaction as the claim: if the
action fails, the ticket is not used up.
"""

from __future__ import annotations

from fastapi import APIRouter

from techradar.api.deps import AppSession, Now, WebSession
from techradar.api.schemas import ConfirmRequest, ConfirmResponse
from techradar.tickets import run_confirmed

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(
    body: ConfirmRequest, session_id: WebSession, session: AppSession, now: Now
) -> ConfirmResponse:
    result, message = await run_confirmed(session, body.token, session_id, now)
    await session.commit()
    return ConfirmResponse(result=result, message=message)
