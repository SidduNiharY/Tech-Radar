"""run_role_test with a fake completer and temp eval sets (no model, no network)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from techradar.db.models import ModelTest
from techradar.llm.roles import Role
from techradar.models.bench_run import (
    BenchDeps,
    BenchSetError,
    TestResult,
    UnsupportedRole,
    load_set,
    run_role_test,
    store_result,
)


class FakeCompleter:
    """Answers by schema shape; `mode` picks how good the model is."""

    def __init__(self, mode: str = "good") -> None:
        self.mode = mode
        self.calls = 0

    async def complete(
        self, role: Role, messages: list[dict[str, str]], *, json_schema: dict[str, Any], **kw: Any
    ) -> str:
        self.calls += 1
        props = json_schema.get("properties", {})
        user = messages[-1]["content"]
        if self.mode == "garbage":
            return "not json"
        if "tags" in props:
            return json.dumps({"tags": ["rust"] if "rust" in user else ["python"]})
        if "summary" in props:
            return json.dumps({"summary": "s", "entities": ["x"]})
        # checker: says the key is wrong only when the item's key is X
        return json.dumps({"key_correct": "key: X" not in user})


def _write(path: Path, name: str, items: list[dict[str, Any]]) -> None:
    (path / f"{name}.yaml").write_text(yaml.safe_dump({"version": 1, "items": items}))


@pytest.fixture
def sets(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "tagging",
        [
            {"id": 1, "text": "rust news", "tags": ["rust"]},
            {"id": 2, "text": "py", "tags": ["Python"]},
        ],
    )
    _write(tmp_path, "json_extract", [{"id": 1, "article": "a"}, {"id": 2, "article": "b"}])
    _write(
        tmp_path,
        "mcq_checker",
        [
            {
                "id": 1,
                "question": "q",
                "options": {"A": "a", "B": "b"},
                "key": "X",
                "key_is_wrong": True,
            },
            {
                "id": 2,
                "question": "q",
                "options": {"A": "a", "B": "b"},
                "key": "A",
                "key_is_wrong": False,
            },
        ],
    )
    return tmp_path


def _deps(sets: Path, completer: FakeCompleter) -> BenchDeps:
    return BenchDeps(completer_for=lambda role, tag: completer, sets_dir=sets)


async def test_worker_passes_with_good_model(sets: Path) -> None:
    r = await run_role_test(Role.WORKER, "qwen3.5:9b", _deps(sets, FakeCompleter()))
    assert r.metrics == {"tag_agreement": 1.0, "json_first_try": 1.0}
    assert r.passed


async def test_worker_fails_on_garbage(sets: Path) -> None:
    r = await run_role_test(Role.WORKER, "t", _deps(sets, FakeCompleter("garbage")))
    assert r.metrics == {"tag_agreement": 0.0, "json_first_try": 0.0}
    assert not r.passed


async def test_checker_catches_wrong_key_without_false_flag(sets: Path) -> None:
    r = await run_role_test(Role.CHECKER, "gemma4:e2b-it-qat", _deps(sets, FakeCompleter()))
    assert r.metrics == {"wrong_key_catch": 1.0, "false_flag": 0.0}
    assert r.passed


async def test_missing_set_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(BenchSetError):
        await run_role_test(Role.WORKER, "t", _deps(tmp_path, FakeCompleter()))


async def test_checker_set_needs_both_kinds(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "mcq_checker",
        [{"id": 1, "question": "q", "options": {}, "key": "A", "key_is_wrong": True}],
    )
    with pytest.raises(BenchSetError):
        await run_role_test(Role.CHECKER, "t", _deps(tmp_path, FakeCompleter()))


async def test_other_roles_unsupported(sets: Path) -> None:
    with pytest.raises(UnsupportedRole):
        await run_role_test(Role.EMBED, "bge-m3", _deps(sets, FakeCompleter()))


@pytest.mark.parametrize("name", ["tagging", "json_extract", "mcq_checker"])
def test_example_sets_load(name: str) -> None:
    root = Path(__file__).resolve().parents[2] / "evals" / "sets"
    example = yaml.safe_load((root / f"{name}.example.yaml").read_text())
    assert example["suite"] == name and example["items"]


def test_load_set_rejects_empty(tmp_path: Path) -> None:
    (tmp_path / "x.yaml").write_text("items: []")
    with pytest.raises(BenchSetError):
        load_set(tmp_path, "x")


@pytest.mark.db
async def test_store_result_writes_model_tests_row(session) -> None:
    tid = await store_result(
        session, Role.WORKER, "t:1", TestResult(metrics={"tag_agreement": 1.0}, passed=True)
    )
    row = await session.get(ModelTest, tid)
    assert row is not None and row.passed and row.role == "worker"
