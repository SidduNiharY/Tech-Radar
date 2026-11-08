"""Read-only MCP server interface for Claude Code on macOS to search vault notes (SEC-24)."""

import os
from pathlib import Path
from typing import Any


class SecurityError(ValueError):
    """Raised when path traversal, symlink breakout, or other security violations occur."""


class VaultMcpServer:
    """Read-only server providing secure search and note reading over an Obsidian vault."""

    def __init__(self, vault_dir: Path | str) -> None:
        self.vault_dir = Path(vault_dir).resolve()
        if not self.vault_dir.exists():
            raise FileNotFoundError(f"Vault directory does not exist: {vault_dir}")
        if not self.vault_dir.is_dir():
            raise NotADirectoryError(f"Vault path is not a directory: {vault_dir}")

    def _validate_path(self, relative_path: str | Path) -> Path:
        """Enforce strict SEC-24 path traversal prevention.

        Rejects:
        - Absolute paths (raises SecurityError).
        - '..' traversal segments (raises SecurityError).
        - Symlinks pointing outside vault_dir (raises SecurityError).
        - Any resolved destination outside vault_dir (raises SecurityError).
        """
        raw_str = str(relative_path).strip()
        if not raw_str:
            raise SecurityError("Relative path must not be empty")

        if raw_str.startswith("/") or raw_str.startswith("\\"):
            raise SecurityError(f"Absolute paths not permitted: {relative_path}")

        rel = Path(raw_str)
        if rel.is_absolute():
            raise SecurityError(f"Absolute paths not permitted: {relative_path}")

        if ".." in rel.parts:
            raise SecurityError(f"Path traversal ('..') not permitted: {relative_path}")

        dest = self.vault_dir / rel
        resolved_vault = self.vault_dir.resolve()

        # Check each component from vault_dir down to dest for external symlinks
        curr = self.vault_dir
        for part in rel.parts:
            curr = curr / part
            if curr.is_symlink():
                resolved_link = curr.resolve()
                if not (
                    resolved_link == resolved_vault
                    or resolved_link.is_relative_to(resolved_vault)
                    or str(resolved_link).startswith(str(resolved_vault) + os.sep)
                ):
                    raise SecurityError(f"Symlink points outside vault: {relative_path}")

        resolved_dest = dest.resolve()
        if not (
            resolved_dest == resolved_vault
            or resolved_dest.is_relative_to(resolved_vault)
            or str(resolved_dest).startswith(str(resolved_vault) + os.sep)
        ):
            raise SecurityError(f"Path traversal outside vault: {relative_path}")

        return dest

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

        q = query.strip().lower()
        if not q or max_results <= 0:
            return []

        resolved_vault = self.vault_dir.resolve()
        candidates: list[dict[str, Any]] = []

        for p in self.vault_dir.rglob("*.md"):
            # Skip hidden files or directories
            try:
                rel = p.relative_to(self.vault_dir)
            except ValueError:
                continue

            if any(part.startswith(".") for part in rel.parts):
                continue

            # Check symlink breakout safety
            try:
                resolved_p = p.resolve()
                if not (
                    resolved_p.is_relative_to(resolved_vault)
                    or str(resolved_p).startswith(str(resolved_vault) + os.sep)
                ):
                    continue
            except OSError, ValueError:
                continue

            if not p.is_file():
                continue

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
        """Read Markdown note content enforcing SEC-24 path traversal prevention."""
        dest = self._validate_path(relative_path)
        if not dest.exists() or not dest.is_file():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        return dest.read_text(encoding="utf-8")

    def list_topics(self, subfolder: str = "") -> list[str]:
        """Safely list topics and notes in vault_dir or the given subfolder."""
        target = self.vault_dir
        if subfolder:
            target = self._validate_path(subfolder)
            if not target.exists():
                raise FileNotFoundError(f"Subfolder not found: {subfolder}")
            if not target.is_dir():
                raise NotADirectoryError(f"Subfolder is not a directory: {subfolder}")

        resolved_vault = self.vault_dir.resolve()
        items: list[str] = []

        for entry in sorted(target.iterdir()):
            if entry.name.startswith("."):
                continue

            try:
                resolved_entry = entry.resolve()
                if not (
                    resolved_entry.is_relative_to(resolved_vault)
                    or str(resolved_entry).startswith(str(resolved_vault) + os.sep)
                ):
                    continue
            except OSError, ValueError:
                continue

            if entry.is_dir() or (entry.is_file() and entry.suffix == ".md"):
                items.append(entry.name)

        return items
