"""Tests for pipeline tables and models."""

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from techradar.db.models import (
    Base,
    Fact,
    FactSource,
    Item,
    Note,
    QuarantineItem,
    RawItem,
    Source,
)


def test_pipeline_tables_registered_in_metadata():
    expected_tables = {
        "techradar.audit_log",
        "techradar.sources",
        "techradar.fetch_runs",
        "techradar.raw_items",
        "techradar.items",
        "techradar.facts",
        "techradar.fact_changes",
        "techradar.intake_log",
        "techradar.quarantine_items",
        "techradar.fact_sources",
        "techradar.notes",
    }
    for table_name in expected_tables:
        assert table_name in Base.metadata.tables, f"Table {table_name} missing from Base.metadata"


def test_source_model_columns():
    cols = Source.__table__.columns
    assert isinstance(cols["id"].type, BigInteger)
    assert cols["id"].primary_key
    assert isinstance(cols["name"].type, String)
    assert cols["name"].type.length == 80
    assert cols["name"].unique is True
    assert isinstance(cols["url"].type, Text)
    assert cols["url"].unique is True
    assert isinstance(cols["interval_min"].type, Integer)


def test_raw_item_model_columns():
    cols = RawItem.__table__.columns
    assert isinstance(cols["url_hash"].type, String)
    assert cols["url_hash"].unique is True
    assert isinstance(cols["source_id"].type, BigInteger)
    assert any(
        fk.target_fullname == "techradar.sources.id" for fk in cols["source_id"].foreign_keys
    )


def test_item_model_columns():
    cols = Item.__table__.columns
    assert cols["raw_item_id"].unique is True
    assert any(
        fk.target_fullname == "techradar.raw_items.id" for fk in cols["raw_item_id"].foreign_keys
    )
    assert isinstance(cols["exam_tags"].type, ARRAY)
    assert isinstance(cols["flags"].type, ARRAY)
    assert isinstance(cols["reader_json"].type, JSONB)


def test_fact_model_columns():
    cols = Fact.__table__.columns
    assert cols["fact_key"].unique is True
    assert isinstance(cols["first_seen_at"].type, DateTime)
    assert isinstance(cols["as_of"].type, Date)


def test_fact_source_composite_pk():
    table = FactSource.__table__
    pk_cols = [c.name for c in table.primary_key.columns]
    assert "fact_id" in pk_cols
    assert "item_id" in pk_cols


def test_quarantine_items_expiry():
    cols = QuarantineItem.__table__.columns
    assert cols["job_id"].unique is True
    assert cols["expires_at"].server_default is not None


def test_note_model_columns():
    cols = Note.__table__.columns
    assert cols["vault_path"].unique is True
    assert cols["cluster_id"].unique is True
    assert isinstance(cols["source_domains"].type, ARRAY)
    assert isinstance(cols["source_urls"].type, ARRAY)
