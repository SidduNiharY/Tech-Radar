from __future__ import annotations

import httpx


async def free_gpu(client: httpx.AsyncClient, ollama_url: str) -> list[str]:
    """Unload every model Ollama has loaded; returns the unloaded model names."""
    base = ollama_url.rstrip("/")
    resp = await client.get(f"{base}/api/ps")
    resp.raise_for_status()
    names = [m["name"] for m in resp.json().get("models", [])]
    for name in names:
        r = await client.post(f"{base}/api/generate", json={"model": name, "keep_alive": 0})
        r.raise_for_status()
    return names
