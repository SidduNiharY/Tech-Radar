import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_deps import direct_python_deps, lookalikes  # noqa: E402


def run_check_deps(*args: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "check_deps.py"), *args]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def test_lookalike_dependency_fails():
    r = run_check_deps("--pyproject", "tests/security/fixtures/deps/pyproject_lookalike.toml")
    assert r.returncode == 1 and "unapproved: reqeusts (looks like: requests)" in r.stdout


def test_repo_dependencies_all_approved():
    assert run_check_deps().returncode == 0


def test_normalises_names_and_strips_extras():
    deps = direct_python_deps(
        {"project": {"dependencies": ["psycopg[binary]>=3", "Pydantic_Settings"]}}
    )
    assert deps == {"psycopg", "pydantic-settings"}


def test_lookalikes():
    assert lookalikes("reqeusts", ["requests", "numpy"]) == ["requests"]
    assert lookalikes("requests", ["requests"]) == []
