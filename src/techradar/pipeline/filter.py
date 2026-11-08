"""Duplicate clustering and relevance filter."""

import math
from collections.abc import Sequence
from pathlib import Path

import yaml


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Compute cosine similarity between two vectors. Returns 0.0 if either is all zeros."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def assign_cluster(
    vec: Sequence[float],
    recent: Sequence[tuple[int, Sequence[float]]],
    threshold: float = 0.90,
) -> int | None:
    """Assign vector to best matching recent cluster above threshold, or None."""
    best_id: int | None = None
    best_score = -1.0
    for cluster_id, cand_vec in recent:
        score = cosine(vec, cand_vec)
        if score >= threshold and score > best_score:
            best_score = score
            best_id = cluster_id
    return best_id


def relevance(vec: Sequence[float], profile: Sequence[Sequence[float]]) -> float:
    """Compute maximum cosine similarity to any profile vector, or 0.0 if empty."""
    if not profile:
        return 0.0
    return max((cosine(vec, p) for p in profile), default=0.0)


def profile_texts(vault_root: Path) -> list[str]:
    """Extract profile text entries from interests.md and syllabus front matter."""
    texts: list[str] = []

    interests_path = vault_root / "context" / "interests.md"
    if interests_path.exists():
        for line in interests_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                texts.append(stripped)

    syllabus_dir = vault_root / "syllabus"
    if syllabus_dir.exists():
        for path in sorted(syllabus_dir.rglob("*.md")):
            content = path.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        data = yaml.safe_load(parts[1])
                        if isinstance(data, dict) and "title" in data:
                            title = str(data["title"]).strip()
                            if title:
                                texts.append(title)
                    except yaml.YAMLError:
                        continue

    return texts
