"""`/skill <name> <status>` through the bot handler (Phase 5 Task 5). SEC-26."""

from datetime import UTC, datetime
from pathlib import Path

from techradar.bot.planner_commands import SKILL_USAGE, handle_planner_command, split_skill_arg

NOW = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)


def test_split_skill_arg():
    assert split_skill_arg("FastAPI learning") == ("FastAPI", "learning")
    assert split_skill_arg("Machine Learning Built") == ("Machine Learning", "built")
    assert split_skill_arg("FastAPI") is None
    assert split_skill_arg("") is None


async def test_unknown_skill(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    reply = await handle_planner_command("skill", "Cobol learning", {"vault_root": tmp_path}, NOW)
    assert reply == "No skill page called Cobol."
    assert list((tmp_path / "skills").iterdir()) == []  # nothing written


async def test_bad_status_and_usage(tmp_path: Path):
    bot_data = {"vault_root": tmp_path}
    assert await handle_planner_command("skill", "FastAPI", bot_data, NOW) == SKILL_USAGE
    assert (
        await handle_planner_command("skill", "FastAPI expert", bot_data, NOW)
        == "Status must be not_started, learning or built."
    )


async def test_skill_updates_page_and_keeps_body(tmp_path: Path):
    (tmp_path / "skills").mkdir()
    page = tmp_path / "skills" / "fastapi.md"
    page.write_text("---\nkind: skill\nstatus: not_started\n---\n# FastAPI\nmy notes\n")
    reply = await handle_planner_command("skill", "FastAPI learning", {"vault_root": tmp_path}, NOW)
    assert reply == "Updated FastAPI: learning."
    text = page.read_text()
    assert "status: learning" in text and text.endswith("# FastAPI\nmy notes\n")


async def test_skill_page_that_is_a_symlink_is_not_written(tmp_path: Path):
    outside = tmp_path / "outside.md"
    outside.write_text("---\nstatus: not_started\n---\nsecret\n")
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "fastapi.md").symlink_to(outside)
    reply = await handle_planner_command("skill", "FastAPI built", {"vault_root": tmp_path}, NOW)
    assert reply == "No skill page called FastAPI."
    assert "not_started" in outside.read_text()


async def test_skill_path_traversal_is_slugged(tmp_path: Path):
    reply = await handle_planner_command(
        "skill", "../../etc/passwd learning", {"vault_root": tmp_path}, NOW
    )
    assert reply == "No skill page called ../../etc/passwd."
