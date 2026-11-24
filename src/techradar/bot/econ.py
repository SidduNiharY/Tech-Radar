"""/econ in the bot (Phase 7 Task 7): read the stored economy series, or add a manual value.

`/econ` alone answers from `econ_series` (no fetching). `/econ <series> <YYYY-MM> <value>`
stores one value for a manual series (USD/INR, gold, petrol). The router passes this only
from the owner's own chat (SEC-26).

SEC: SEC-26.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from techradar.world.econ import parse_econ_command, record_manual, render_econ

NOT_AVAILABLE = "Not available yet."


async def handle_econ(update: Any, bot_data: Mapping[str, Any], arg: str) -> None:
    message = update.message
    session_factory = bot_data.get("session_factory")
    if session_factory is None:
        await message.reply_text(NOT_AVAILABLE)
        return
    if not arg.strip():
        async with session_factory() as session:
            await message.reply_text(await render_econ(session))
        return
    parsed = parse_econ_command(arg)
    if isinstance(parsed, str):
        await message.reply_text(parsed)
        return
    series, period, value = parsed
    async with session_factory() as session:
        await record_manual(session, series, period, value)
        await session.commit()
    await message.reply_text("Saved.")
