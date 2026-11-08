"""Safe Markdown note writer with StrictUndefined Jinja2 templates."""

import os
import re
import secrets
import unicodedata
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

import jinja2
import yaml
from pydantic import BaseModel, ConfigDict

from techradar.schemas.pipeline import ExamTag, FourQuestions, Section

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "vault" / "templates"


class StorySource(BaseModel):
    """Provenance metadata for an item source."""

    model_config = ConfigDict(extra="forbid")

    url: str
    domain: str
    fetched_at: datetime


class StoryFact(BaseModel):
    """Fact statement with verification status and supporting source count."""

    model_config = ConfigDict(extra="forbid")

    statement: str
    status: Literal["verified", "unverified"]
    source_count: int


class StoryNote(BaseModel):
    """Aggregate model representing a rendered story note."""

    model_config = ConfigDict(extra="forbid")

    cluster_id: int
    title: str
    published: date
    section: Section
    exam_tags: list[ExamTag]
    summary: str
    four_questions: FourQuestions
    facts: list[StoryFact]
    sources: list[StorySource]
    verified_headline: bool
    is_flagged: bool = False


_ESCAPE_REPLACEMENTS = [
    ("\\", r"\\"),
    ("`", r"\`"),
    ("*", r"\*"),
    ("_", r"\_"),
    ("[", r"\["),
    ("]", r"\]"),
    ("(", r"\("),
    (")", r"\)"),
    ("<", r"\<"),
    (">", r"\>"),
    ("#", r"\#"),
    ("|", r"\|"),
    ("!", r"\!"),
]


def md_escape(s: str) -> str:
    """Backslash-escapes markdown characters: \\ ` * _ [ ] ( ) < > # | !"""
    res = s
    for char, rep in _ESCAPE_REPLACEMENTS:
        res = res.replace(char, rep)
    return res


def slugify(title: str, max_len: int = 80) -> str:
    """Convert title to ASCII kebab-case slug; returns 'note' if empty."""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    slug = slug[:max_len].rstrip("-")
    return slug or "note"


def note_rel_path(published: date, title: str, taken: set[str]) -> PurePosixPath:
    """Generate relative vault path for story note, handling collisions."""
    slug = slugify(title)
    base = f"wiki/news/{published.year:04d}/{published.month:02d}/{slug}"
    cand = f"{base}.md"
    if cand not in taken:
        return PurePosixPath(cand)
    counter = 2
    while f"{base}-{counter}.md" in taken:
        counter += 1
    return PurePosixPath(f"{base}-{counter}.md")


def render_story(note: StoryNote) -> str:
    """Render StoryNote to Markdown through story.md.j2 template."""
    front_matter_data = {
        "kind": "news",
        "cluster_id": note.cluster_id,
        "title": note.title,
        "published": note.published.isoformat(),
        "section": note.section.value,
        "exam_tags": [tag.value for tag in note.exam_tags],
        "verified_headline": note.verified_headline,
        "sources": [s.url for s in note.sources],
        "generated": True,
    }
    fm_yaml = yaml.safe_dump(front_matter_data, sort_keys=False, allow_unicode=True)

    escaped_facts = [
        StoryFact(
            statement=md_escape(f.statement),
            status=f.status,
            source_count=f.source_count,
        )
        for f in note.facts
    ]

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,  # noqa: S701 - Markdown output explicitly escaped via md_escape
    )
    template = env.get_template("story.md.j2")

    return template.render(
        front_matter=fm_yaml,
        title=md_escape(note.title),
        summary=md_escape(note.summary),
        what_happened=md_escape(note.four_questions.what_happened),
        why=md_escape(note.four_questions.why),
        what_changes=md_escape(note.four_questions.what_changes),
        how_it_affects_me=md_escape(note.four_questions.how_it_affects_me),
        facts=escaped_facts,
        sources=note.sources,
        is_flagged=note.is_flagged,
    )


def write_note(vault_root: Path, rel: PurePosixPath, content: str) -> Path:
    """Safely and atomically write content to vault without following symlinks."""
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Invalid note relative path: {rel}")

    dest = vault_root / Path(rel)

    # Check for symlinks in path components under vault_root
    curr = vault_root
    for part in rel.parts:
        curr = curr / part
        if curr.is_symlink():
            raise ValueError(f"Refusing to write through symlink: {curr}")

    resolved_root = vault_root.resolve()
    resolved_dest = dest.resolve()
    if not str(resolved_dest).startswith(str(resolved_root)):
        raise ValueError(f"Path traversal detected: {rel}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest.with_name(f"{dest.name}.{secrets.token_hex(4)}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.chmod(tmp_path, 0o644)
    os.replace(tmp_path, dest)
    return dest
