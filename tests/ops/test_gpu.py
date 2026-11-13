from __future__ import annotations

import json

import httpx
import respx

from techradar.ops.gpu import free_gpu

URL = "http://ollama:11434"


async def test_free_gpu_unloads_each_loaded_model(respx_mock: respx.MockRouter):
    respx_mock.get(f"{URL}/api/ps").respond(
        json={"models": [{"name": "qwen3:14b"}, {"name": "bge-m3"}]}
    )
    gen = respx_mock.post(f"{URL}/api/generate").respond(json={"done": True})
    async with httpx.AsyncClient() as client:
        names = await free_gpu(client, URL)
    assert names == ["qwen3:14b", "bge-m3"]
    bodies = [json.loads(c.request.content) for c in gen.calls]
    assert bodies == [
        {"model": "qwen3:14b", "keep_alive": 0},
        {"model": "bge-m3", "keep_alive": 0},
    ]


async def test_free_gpu_nothing_loaded(respx_mock: respx.MockRouter):
    respx_mock.get(f"{URL}/api/ps").respond(json={"models": []})
    gen = respx_mock.post(f"{URL}/api/generate").respond(json={})
    async with httpx.AsyncClient() as client:
        assert await free_gpu(client, URL) == []
    assert gen.call_count == 0
