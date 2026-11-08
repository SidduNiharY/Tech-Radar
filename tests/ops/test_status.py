import pytest

from techradar.bot.render import render_status
from techradar.ops.status import collect_status


@pytest.mark.asyncio
async def test_status_ollama_down():
    async def up():
        return True

    async def down():
        return None

    s = await collect_status(up, down, lambda: 50.0)
    assert not s.ollama_ok
    assert render_status(s).splitlines()[2] == "Models: down"


@pytest.mark.asyncio
async def test_status_db_down():
    async def no():
        return False

    async def models():
        return []

    s = await collect_status(no, models, lambda: 50.0)
    assert render_status(s).splitlines()[1] == "Database: down"


@pytest.mark.asyncio
async def test_status_all_ok():
    async def up():
        return True

    async def models():
        return ["qwen3.5:4b", "llama3.2:3b"]

    s = await collect_status(up, models, lambda: 85.6)
    assert s.db_ok
    assert s.ollama_ok
    assert s.loaded_models == ["qwen3.5:4b", "llama3.2:3b"]
    assert s.disk_free_pct == 85.6
