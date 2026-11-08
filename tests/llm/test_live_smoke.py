from pathlib import Path

import pytest
from pydantic import BaseModel

from techradar.llm import LiteLLMCompleter, complete_json
from techradar.llm.roles import Role, load_roles


class Out(BaseModel):
    a: int


@pytest.mark.live
async def test_live_smoke() -> None:
    roles = load_roles(Path("infra/models/roles.yaml"))
    completer = LiteLLMCompleter(roles, "http://127.0.0.1:11434")
    result = await complete_json(
        completer,
        Role.WORKER,
        "Return JSON only.",
        "Give a=3",
        Out,
    )
    assert result.a == 3
