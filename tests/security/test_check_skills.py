import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_skills import AllowedExtension, skill_problems  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_unlisted_skill_fails():
    assert skill_problems(FIXTURES / "skills_unlisted", {}) == ["shady-skill: not allowed"]


def test_changed_skill_fails():
    allow = {
        "helper": AllowedExtension(
            name="helper",
            kind="skill",
            source="https://github.com/example/skills",
            commit="0" * 40,
            sha256="0" * 64,
            why="test",
        )
    }
    assert skill_problems(FIXTURES / "skills_changed", allow) == ["helper: changed"]
