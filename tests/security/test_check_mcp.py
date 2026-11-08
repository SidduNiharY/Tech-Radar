import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_mcp import AllowedServer, mcp_problems  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "deps"


def load(filename: str) -> dict:
    with open(FIXTURES / filename, encoding="utf-8") as f:
        return json.load(f)


def test_mcp_unlisted_server_fails():
    assert mcp_problems(load("mcp_unlisted.json"), {}) == ["shady-tools: not allowed"]


def test_mcp_latest_fails():
    allow = {
        "vault": AllowedServer(
            name="vault", command="uvx", version="1.0.0", access="read", why="notes"
        )
    }
    assert "vault: not pinned" in mcp_problems(load("mcp_latest.json"), allow)
