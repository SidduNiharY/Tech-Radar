from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from techradar.vault.frontmatter import (
    SKILL_STATUSES,
    set_skill_status,
    update_front_matter,
)

TODAY = date(2026, 11, 8)


def test_front_matter_update_keeps_body():
    md = "---\nkind: skill\nstatus: not_started\n---\n# FastAPI\nmy notes\n"
    out = update_front_matter(md, {"status": "learning"}, frozenset({"status", "updated"}))
    assert out.endswith("# FastAPI\nmy notes\n")
    assert "status: learning" in out
    assert "kind: skill" in out


def test_front_matter_rejects_other_keys():
    with pytest.raises(ValueError, match="Disallowed frontmatter key"):
        update_front_matter("---\na: 1\n---\n", {"kind": "x"}, frozenset({"status"}))


def test_front_matter_creates_block_if_none():
    md = "# Plain Note\nNo frontmatter here.\n"
    out = update_front_matter(md, {"status": "built"}, frozenset({"status"}))
    assert out.startswith("---\nstatus: built\n---\n")
    assert out.endswith("# Plain Note\nNo frontmatter here.\n")


@pytest.mark.asyncio
async def test_set_skill_status_invalid_status(tmp_path: Path):
    assert "not_started" in SKILL_STATUSES
    res = await set_skill_status(tmp_path, "Python", "mastered", TODAY)
    assert res == "Status must be not_started, learning or built."


@pytest.mark.asyncio
async def test_set_skill_status_unknown_skill(tmp_path: Path):
    res = await set_skill_status(tmp_path, "Cobol", "learning", TODAY)
    assert res == "No skill page called Cobol."


@pytest.mark.asyncio
async def test_set_skill_status_success(tmp_path: Path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skills_dir / "fastapi.md"
    skill_file.write_text(
        "---\nkind: skill\nstatus: not_started\n---\n# FastAPI\nDeep framework notes.\n",
        encoding="utf-8",
    )

    res = await set_skill_status(tmp_path, "FastAPI", "learning", TODAY)
    assert res == "Updated FastAPI: learning."

    updated_content = skill_file.read_text(encoding="utf-8")
    assert "status: learning" in updated_content
    assert "updated: '2026-11-08'" in updated_content or "updated: 2026-11-08" in updated_content
    assert updated_content.endswith("# FastAPI\nDeep framework notes.\n")


import pytest as _pytest  # noqa: E402


@_pytest.mark.parametrize(
    ("md", "body"),
    [
        ("---\n---\nbody\n", "body\n"),  # empty front matter
        ("---\nstatus: learning\n---", ""),  # front matter ends the file
        ("---\nstatus: learning\n---\r\nbody", "body"),  # CRLF after the fence
    ],
)
def test_update_never_adds_a_second_block(md, body):
    out = update_front_matter(md, {"status": "built"}, frozenset({"status"}))
    assert out.count("---") == 2, out
    assert out == f"---\nstatus: built\n---\n{body}"
