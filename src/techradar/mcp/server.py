"""Read-only MCP server interface for Claude Code on macOS to search vault notes (SEC-24).

Rules from Phase 10 Task 8: only `.md` files, never through a symlink at any
level (an in-vault link can be retargeted later), at most MAX_NOTE_BYTES per
note, and at most MAX_LIMIT search results.
"""

import os
from pathlib import Path
from typing import Any

MAX_NOTE_BYTES = 200_000
MAX_LIMIT = 10


class SecurityError(ValueError):
    """Raised when path traversal, symlink breakout, or other security violations occur."""


def _safe_path(vault: Path, rel: str | Path) -> Path:
    """Resolve `rel` inside `vault`, refusing absolute paths, `..` and any symlink."""
    raw = str(rel).strip()
    if not raw:
        raise SecurityError("Relative path must not be empty")
    if raw.startswith(("/", "\\")) or Path(raw).is_absolute():
        raise SecurityError(f"Absolute paths not permitted: {rel}")
    parts = Path(raw).parts
    if ".." in parts:
        raise SecurityError(f"Path traversal ('..') not permitted: {rel}")
    vault = vault.resolve()
    curr = vault
    for part in parts:
        curr = curr / part
        if curr.is_symlink():
            raise SecurityError(f"Symlinks are not followed: {rel}")
    if not curr.resolve().is_relative_to(vault):
        raise SecurityError(f"Path traversal outside vault: {rel}")
    return curr


def safe_note_path(vault: Path, rel: str) -> Path:
    """A note path inside `vault`, ending in .md, with no symlink at any level."""
    path = _safe_path(vault, rel)
    if path.suffix != ".md":
        raise SecurityError(f"Only .md notes can be read: {rel}")
    return path


class VaultMcpServer:
    """Read-only server providing secure search and note reading over an Obsidian vault."""

    def __init__(self, vault_dir: Path | str) -> None:
        self.vault_dir = Path(vault_dir).resolve()
        if not self.vault_dir.exists():
            raise FileNotFoundError(f"Vault directory does not exist: {vault_dir}")
        if not self.vault_dir.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {vault_dir}")

    def _validate_path(self, relative_path: str | Path) -> Path:
        """A path inside the vault with no `..`, no absolute start and no symlink."""
        return _safe_path(self.vault_dir, relative_path)

    def search_notes(
        self,
        query: str,
        max_results: int = 10,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search Markdown notes in vault_dir across filename, frontmatter, and body text.

        Title matches rank first. Limit capped by max_results or explicit limit.
        """
        if limit is not None:
            max_results = limit
        max_results = min(max_results, MAX_LIMIT)

        q = query.strip().lower()
        if not q or max_results <= 0:
            return []

        candidates: list[dict[str, Any]] = []

        for p in self._markdown_files():
            rel = p.relative_to(self.vault_dir)
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Parse frontmatter, title, and body
            frontmatter_text = ""
            body_text = content
            title = ""

            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_text = parts[1]
                    body_text = parts[2]
                    for line in frontmatter_text.splitlines():
                        line_s = line.strip()
                        if line_s.startswith("title:"):
                            title = line_s.split("title:", 1)[1].strip().strip("\"'")
                            break

            if not title:
                for line in body_text.splitlines():
                    line_s = line.strip()
                    if line_s.startswith("# "):
                        title = line_s[2:].strip()
                        break

            if not title:
                title = p.stem.replace("-", " ").replace("_", " ").title()

            # Ranking: title matches rank first (score 0), then filename (1),
            # frontmatter (2), body (3)
            rel_path_str = rel.as_posix()
            if q in title.lower():
                score = 0
            elif q in p.name.lower() or q in rel_path_str.lower():
                score = 1
            elif q in frontmatter_text.lower():
                score = 2
            elif q in body_text.lower():
                score = 3
            else:
                continue

            # Extract snippet around match
            snippet = ""
            idx = content.lower().find(q)
            if idx != -1:
                start = max(0, idx - 50)
                end = min(len(content), idx + len(q) + 90)
                raw_snip = content[start:end].replace("\n", " ").strip()
                snippet = f"...{raw_snip}..." if start > 0 else raw_snip
            else:
                first_lines = [line.strip() for line in body_text.splitlines() if line.strip()]
                snippet = first_lines[0][:120] if first_lines else title

            candidates.append(
                {
                    "score": score,
                    "path": rel_path_str,
                    "title": title,
                    "snippet": snippet,
                }
            )

        # Sort: lowest score first (title matches rank first), then alphabetical by title
        candidates.sort(key=lambda item: (item["score"], item["title"].lower()))

        return [
            {
                "path": item["path"],
                "title": item["title"],
                "snippet": item["snippet"],
            }
            for item in candidates[:max_results]
        ]

    def read_note(self, relative_path: str) -> str:
        """Read one Markdown note (SEC-24 path rules, at most MAX_NOTE_BYTES)."""
        dest = safe_note_path(self.vault_dir, relative_path)
        if not dest.is_file():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        if dest.stat().st_size > MAX_NOTE_BYTES:
            raise SecurityError(f"Note is larger than {MAX_NOTE_BYTES} bytes: {relative_path}")
        return dest.read_text(encoding="utf-8")

    def _markdown_files(self) -> list[Path]:
        """Visible .md files under the vault, never through a symlink, within the size cap."""
        found: list[Path] = []
        for root, dirs, files in os.walk(self.vault_dir, followlinks=False):
            base = Path(root)
            dirs[:] = sorted(
                d for d in dirs if not d.startswith(".") and not (base / d).is_symlink()
            )
            for name in sorted(files):
                f = base / name
                if name.startswith(".") or f.suffix != ".md" or f.is_symlink():
                    continue
                try:
                    if f.stat().st_size > MAX_NOTE_BYTES:
                        continue
                except OSError:
                    continue
                found.append(f)
        return found

    def list_topics(self, subfolder: str = "") -> list[str]:
        """Safely list topics and notes in vault_dir or the given subfolder."""
        target = self.vault_dir
        if subfolder:
            target = self._validate_path(subfolder)
            if not target.exists():
                raise FileNotFoundError(f"Subfolder not found: {subfolder}")
            if not target.is_dir():
                raise NotADirectoryError(f"Subfolder is not a directory: {subfolder}")

        items: list[str] = []

        for entry in sorted(target.iterdir()):
            if entry.name.startswith(".") or entry.is_symlink():
                continue

            if entry.is_dir() or (entry.is_file() and entry.suffix == ".md"):
                items.append(entry.name)

        return items
