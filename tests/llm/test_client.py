import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

# Ensure repo root is on sys.path for test imports
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from techradar.llm.client import (  # noqa: E402
    LLMOutputError,
    complete_json,
    strip_thinking,
)
from techradar.llm.roles import Role  # noqa: E402
from tests.fakes import FakeCompleter, FakeEmbedder  # noqa: E402


class Out(BaseModel):
    a: int


def test_strip_thinking_removes_block() -> None:
    assert strip_thinking('<think>plan</think>\n{"a": 1}') == '{"a": 1}'
    assert (
        strip_thinking(
            """<think>
some long internal
thoughts
</think>
{"b": 2}"""
        )
        == '{"b": 2}'
    )
    assert strip_thinking('{"a": 1}') == '{"a": 1}'


async def test_complete_json_returns_model() -> None:
    fc = FakeCompleter(['{"a": 1}'])
    res = await complete_json(fc, Role.WORKER, "sys", "user", Out)
    assert res.a == 1
    assert len(fc.calls) == 1
    assert fc.calls[0]["role"] == Role.WORKER
    assert fc.calls[0]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "user"},
    ]
    assert "properties" in fc.calls[0]["json_schema"]


async def test_complete_json_retries_once_then_raises() -> None:
    fc = FakeCompleter(["not json", '{"a": "x"}'])
    with pytest.raises(LLMOutputError):
        await complete_json(fc, Role.WORKER, "s", "u", Out)
    assert len(fc.calls) == 2


async def test_complete_json_accepts_think_prefix() -> None:
    fc = FakeCompleter(['<think>x</think>{"a": 2}'])
    res = await complete_json(fc, Role.WORKER, "s", "u", Out)
    assert res.a == 2


async def test_complete_json_recovers_on_second_attempt() -> None:
    fc = FakeCompleter(["garbage", '{"a": 42}'])
    res = await complete_json(fc, Role.WORKER, "s", "u", Out)
    assert res.a == 42
    assert len(fc.calls) == 2


async def test_fake_embedder() -> None:
    embedder = FakeEmbedder(dim=3, table={"hello": [1.0, 2.0, 3.0]})
    vecs = await embedder.embed(["hello", "world"])
    assert vecs == [[1.0, 2.0, 3.0], [0.0, 0.0, 0.0]]
    assert embedder.calls == [["hello", "world"]]
