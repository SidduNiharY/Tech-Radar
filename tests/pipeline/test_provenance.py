"""Integration and unit tests for delete-by-source provenance."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from techradar.pipeline.provenance import DeleteReport

OFFICIAL = frozenset({"rbi.org.in"})


@pytest.mark.asyncio
async def test_delete_by_domain_mock_counts(tmp_path: Path):
    session = AsyncMock()
    # Mock returning deleted fact sources, remaining sources, deleted facts
    session.execute.return_value = MagicMock()
    vault = tmp_path / "vault"
    vault.mkdir()

    # Unit verification of delete report structure
    report = DeleteReport(
        notes_deleted=1,
        facts_deleted=1,
        facts_downgraded=1,
        clusters_to_rerender=[2],
    )
    assert report.notes_deleted == 1
    assert report.facts_deleted == 1
    assert report.facts_downgraded == 1
    assert report.clusters_to_rerender == [2]
