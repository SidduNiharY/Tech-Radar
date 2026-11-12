"""Tests for worker ask and save_answer tasks (Phase 2b Task 6).

SEC: SEC-37, SEC-39, SEC-41.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from techradar.db.engine import make_engine
from techradar.db.models import Answer as AnswerModel
from techradar.settings import Settings
from techradar.worker.tasks import ask_job, save_answer_job


def test_ask_jobs_use_llm_queue_and_lock() -> None:
    assert (ask_job.queue, ask_job.lock) == ("llm", "ask")
    assert (save_answer_job.queue, save_answer_job.lock) == ("llm", "ask")


@pytest.fixture
def db_settings() -> Settings:
    return Settings(
        telegram_owner_chat_id=1,
        db_host="127.0.0.1",
        db_port=55432,
        db_name="techradar",
        secrets_dir=Path("secrets"),
    )


@pytest.fixture
async def seed_answer(
    db_settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[int]:
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    job_settings = db_settings.model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr("techradar.worker.tasks._get_settings", lambda: job_settings)

    app_engine = make_engine("app", db_settings)
    session_factory = async_sessionmaker(app_engine, expire_on_commit=False)

    ans_id: int
    async with session_factory() as session:
        ans = AnswerModel(
            chat_id=1,
            question="What is the repo rate?",
            text="RBI repo rate is 6.5%.",
            citations=[{"doc_path": "notes/policy.md", "title": "RBI"}],
            status="answered",
            used_unverified=False,
            flags=[],
        )
        session.add(ans)
        await session.commit()
        await session.refresh(ans)
        ans_id = ans.id

    try:
        yield ans_id
    finally:
        async with session_factory() as session:
            await session.execute(
                text(
                    "DELETE FROM techradar.outbox WHERE ref_id = :id AND purpose = 'answer_saved'"
                ),
                {"id": ans_id},
            )
            await session.execute(
                text("DELETE FROM techradar.answers WHERE id = :id"),
                {"id": ans_id},
            )
            await session.commit()
        await app_engine.dispose()


@pytest.mark.db
async def test_save_answer_writes_generated_note(
    seed_answer: int,
    tmp_path: Path,
) -> None:
    await save_answer_job(answer_id=seed_answer)
    answer_files = list((tmp_path / "vault" / "wiki" / "answers").rglob("*.md"))
    assert len(answer_files) == 1
    content = answer_files[0].read_text(encoding="utf-8")
    assert "generated: true" in content
    assert "kind: answer" in content
    assert "What is the repo rate?" in content
    assert "RBI repo rate is 6.5%." in content
