"""Vault skeleton generator from seed configurations."""

import argparse
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from techradar.pipeline.writer import slugify, write_note


def generate_skeleton(vault_root: Path, seed_dir: Path) -> list[Path]:
    """Create initial vault structure and seeded pages; never overwrites existing files."""
    created: list[Path] = []
    vault_root.mkdir(parents=True, exist_ok=True)

    # 1. Static seed files
    files_dir = seed_dir / "files"
    if files_dir.exists():
        for src_path in sorted(files_dir.rglob("*")):
            if src_path.is_file():
                rel = src_path.relative_to(files_dir)
                dest = vault_root / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
                    dest.chmod(0o644)
                    created.append(dest)

    # 2. Syllabus pages
    syllabus_seed_dir = seed_dir / "syllabus"
    if syllabus_seed_dir.exists():
        for yaml_path in sorted(syllabus_seed_dir.glob("*.yaml")):
            exam = yaml_path.stem
            data: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for item in data.get("subjects", []):
                title = item["title"]
                slug = slugify(title)
                rel_posix = PurePosixPath(f"syllabus/{exam}/{slug}.md")
                dest = vault_root / Path(rel_posix)
                if not dest.exists():
                    content = (
                        f"---\nkind: syllabus\ntitle: {title}\nstatus: not_started\n---\n\n"
                        f"# {title}\n"
                    )
                    write_note(vault_root, rel_posix, content)
                    created.append(dest)

    # 3. Foundations pages
    foundations_yaml = seed_dir / "foundations.yaml"
    if foundations_yaml.exists():
        fdata: dict[str, Any] = yaml.safe_load(foundations_yaml.read_text(encoding="utf-8")) or {}
        for area, topics in fdata.get("foundations", {}).items():
            for topic in topics:
                title = topic["title"]
                slug = slugify(title)
                rel_posix = PurePosixPath(f"foundations/{area}/{slug}.md")
                dest = vault_root / Path(rel_posix)
                if not dest.exists():
                    content = (
                        f"---\nkind: foundation\ntitle: {title}\nstatus: not_started\n---\n\n"
                        f"# {title}\n"
                    )
                    write_note(vault_root, rel_posix, content)
                    created.append(dest)

    # 4. Skills pages
    skills_yaml = seed_dir / "skills.yaml"
    if skills_yaml.exists():
        sdata: dict[str, Any] = yaml.safe_load(skills_yaml.read_text(encoding="utf-8")) or {}
        for skill in sdata.get("skills", []):
            title = skill["title"]
            slug = slugify(title)
            rel_posix = PurePosixPath(f"skills/{slug}.md")
            dest = vault_root / Path(rel_posix)
            if not dest.exists():
                content = (
                    f"---\nkind: skill\ntitle: {title}\nstatus: not_started\n---\n\n# {title}\n"
                )
                write_note(vault_root, rel_posix, content)
                created.append(dest)

    return created


def main() -> None:
    """CLI entrypoint for generating vault skeleton."""
    parser = argparse.ArgumentParser(description="Generate vault skeleton from seed definitions")
    parser.add_argument("--vault", type=Path, required=True, help="Target Obsidian vault directory")
    parser.add_argument(
        "--seed", type=Path, default=Path("vault-seed"), help="Path to seed definitions directory"
    )
    args = parser.parse_args()

    created = generate_skeleton(args.vault, args.seed)
    print(f"Created {len(created)} pages in {args.vault}")


if __name__ == "__main__":
    main()
