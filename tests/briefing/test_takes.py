"""Unit and integration tests for briefing 'My take' replies."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath

import pytest
from sqlalchemy import select

from techradar.briefing.takes import (
    MAX_TAKE_CHARS,
    format_take_entry,
    save_take,
    take_note_entry,
    take_rel_path,
)
from techradar.db.models import Briefing as BriefingModel
from techradar.db.models import Take


class FakeAsyncSession:
    """Mock async session for unit testing save_take without Postgres."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if hasattr(obj, "id"):
            obj.id = len(self.added)

    async def flush(self) -> None:
        self.flushed = True


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


# ============================================================================
# Unit Tests (Run without real Postgres)
# ============================================================================


@pytest.mark.asyncio
async def test_save_take_length_limit(fake_session: FakeAsyncSession):
    now = datetime(2026, 11, 8, 7, 0)

    # > 500 chars returns "too_long"
    too_long_text = "x" * (MAX_TAKE_CHARS + 1)
    res_too_long = await save_take(fake_session, None, 1, too_long_text, now)
    assert res_too_long == "too_long"
    assert len(fake_session.added) == 0

    # Exactly 500 chars returns "saved"
    exact_text = "x" * MAX_TAKE_CHARS
    res_exact = await save_take(fake_session, None, 1, exact_text, now)
    assert res_exact == "saved"
    assert len(fake_session.added) == 1
    stored = fake_session.added[0]
    assert isinstance(stored, Take)
    assert stored.text == exact_text
    assert stored.briefing_id == 1
    assert stored.created_at == now
    assert fake_session.flushed is True


@pytest.mark.asyncio
async def test_save_take_appends_monthly_file_unit(fake_session: FakeAsyncSession, tmp_path: Path):
    now1 = datetime(2026, 11, 8, 7, 0)
    res1 = await save_take(fake_session, tmp_path, 3, "Rates will fall", now1)
    assert res1 == "saved"

    monthly_file = tmp_path / "context" / "takes" / "2026-11.md"
    assert monthly_file.is_file()
    assert monthly_file.read_text(encoding="utf-8") == "- 2026-11-08 07:00 Rates will fall\n"

    # Second take in the same month appends to the existing file
    now2 = datetime(2026, 11, 8, 14, 30)
    res2 = await save_take(fake_session, tmp_path, 3, "Inflation is easing", now2)
    assert res2 == "saved"

    expected_content = (
        "- 2026-11-08 07:00 Rates will fall\n- 2026-11-08 14:30 Inflation is easing\n"
    )
    assert monthly_file.read_text(encoding="utf-8") == expected_content

    # Third take in a different month writes to a new monthly file
    now3 = datetime(2026, 12, 1, 9, 15)
    res3 = await save_take(fake_session, tmp_path, 4, "Year-end review", now3)
    assert res3 == "saved"

    dec_file = tmp_path / "context" / "takes" / "2026-12.md"
    assert dec_file.is_file()
    assert dec_file.read_text(encoding="utf-8") == "- 2026-12-01 09:15 Year-end review\n"
    assert monthly_file.read_text(encoding="utf-8") == expected_content


@pytest.mark.asyncio
async def test_save_take_indian_languages(fake_session: FakeAsyncSession, tmp_path: Path):
    now = datetime(2026, 11, 8, 8, 0)
    hindi_take = "भारतीय रिजर्व बैंक ने रेपो रेट 5.5% पर बरकरार रखा"
    telugu_take = "ద్రవ్యోల్బణం తగ్గుముఖం పడుతోంది, వృద్ధి రేటు బాగుంది"

    # Test Hindi
    res_hi = await save_take(fake_session, tmp_path, 1, hindi_take, now)
    assert res_hi == "saved"
    take_hi = fake_session.added[0]
    assert isinstance(take_hi, Take)
    assert take_hi.text == hindi_take

    # Test Telugu
    now_te = datetime(2026, 11, 8, 9, 0)
    res_te = await save_take(fake_session, tmp_path, 1, telugu_take, now_te)
    assert res_te == "saved"
    take_te = fake_session.added[1]
    assert isinstance(take_te, Take)
    assert take_te.text == telugu_take

    # Verify both Hindi and Telugu appear unchanged in the vault monthly file
    monthly_file = tmp_path / "context" / "takes" / "2026-11.md"
    content = monthly_file.read_text(encoding="utf-8")
    assert hindi_take in content
    assert telugu_take in content


@pytest.mark.asyncio
async def test_save_take_markdown_escaping(fake_session: FakeAsyncSession, tmp_path: Path):
    now = datetime(2026, 11, 8, 10, 0)
    raw_take = "Market will *rise* & [yields] fall! Check #interest | rate"

    res = await save_take(fake_session, tmp_path, 1, raw_take, now)
    assert res == "saved"

    # Stored take in DB retains sanitized raw text
    take = fake_session.added[0]
    assert isinstance(take, Take)
    assert take.text == raw_take

    # Vault note escapes markdown characters
    monthly_file = tmp_path / "context" / "takes" / "2026-11.md"
    content = monthly_file.read_text(encoding="utf-8")
    assert r"\*rise\*" in content
    assert r"\[yields\]" in content
    assert r"\#interest" in content
    assert r"\|" in content
    assert r"\!" in content


@pytest.mark.asyncio
async def test_save_take_without_vault(fake_session: FakeAsyncSession):
    now = datetime(2026, 11, 8, 11, 0)
    res = await save_take(fake_session, None, 5, "No vault specified", now)
    assert res == "saved"
    assert len(fake_session.added) == 1
    assert fake_session.flushed is True


def test_take_helpers():
    now = datetime(2026, 11, 8, 7, 0)
    assert take_rel_path(now) == PurePosixPath("context/takes/2026-11.md")
    assert format_take_entry(now, "Rates will fall") == "- 2026-11-08 07:00 Rates will fall"
    rel, line = take_note_entry(now, "Rates will fall")
    assert rel == PurePosixPath("context/takes/2026-11.md")
    assert line == "- 2026-11-08 07:00 Rates will fall"


# ============================================================================
# Database Integration Tests (Marked with pytestmark = pytest.mark.db)
# ============================================================================


@pytest.mark.db
async def test_save_take_appends_monthly_file(session, tmp_path: Path):
    now = datetime(2026, 11, 8, 7, 0)
    briefing = BriefingModel(date=now.date(), sent_at=now)
    session.add(briefing)
    await session.flush()

    assert await save_take(session, tmp_path, briefing.id, "Rates will fall", now) == "saved"
    assert "Rates will fall" in (tmp_path / "context/takes/2026-11.md").read_text(encoding="utf-8")
    rows = (await session.execute(select(Take).where(Take.briefing_id == briefing.id))).scalars()
    assert [t.text for t in rows] == ["Rates will fall"]


@pytest.mark.db
async def test_save_take_too_long_db(session, tmp_path: Path):
    now = datetime(2026, 11, 8, 7, 0)
    assert await save_take(session, tmp_path, 3, "x" * (MAX_TAKE_CHARS + 1), now) == "too_long"
    assert not (tmp_path / "context").exists()
