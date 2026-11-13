"""Fetch Docling's offline models at image build and verify them (SEC-23).

Owner approval 2026-11-13: the layout model (docling-project/docling-layout-
heron), TableFormer (docling-project/docling-models) and RapidOCR, all
loaded from safetensors or ONNX. Docling downloads from moving branches, so
the files are pinned by content: every file must match
infra/models/docling_models.sha256, no other file may exist, and no
pickle-type file (.pth, .pt, .pkl, .bin, .ckpt) is ever kept. Any change
upstream fails the build until the manifest is updated on purpose.

Usage (image build only): python scripts/fetch_docling_models.py <out_dir> <manifest>
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = (".pth", ".pt", ".pkl", ".pickle", ".bin", ".ckpt")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_models(out_dir: Path, manifest_text: str) -> None:
    """Raise ValueError unless out_dir holds exactly the manifest's files."""
    expected: dict[str, str] = {}
    for line in manifest_text.splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        expected[rel] = digest
    present = {
        p.relative_to(out_dir).as_posix(): p for p in sorted(out_dir.rglob("*")) if p.is_file()
    }
    for rel in present:
        if rel.lower().endswith(FORBIDDEN_SUFFIXES):
            raise ValueError(f"forbidden pickle-type model file: {rel}")
    extra = sorted(set(present) - set(expected))
    if extra:
        raise ValueError(f"files not in the manifest: {extra[:5]}")
    missing = sorted(set(expected) - set(present))
    if missing:
        raise ValueError(f"manifest files missing: {missing[:5]}")
    for rel, digest in expected.items():
        if _sha256(present[rel]) != digest:
            raise ValueError(f"hash mismatch for {rel}")


def fetch(out_dir: Path) -> None:
    """Download the three approved models, then drop caches and pickle copies."""
    from docling.utils.model_downloader import download_models

    download_models(
        output_dir=out_dir,
        with_layout=True,
        with_tableformer=True,
        with_code_formula=False,
        with_picture_classifier=False,
        with_rapidocr=True,
        progress=False,
    )
    for cache in list(out_dir.rglob(".cache")):
        if cache.is_dir():
            shutil.rmtree(cache)
    # RapidOCR ships each model twice; only the ONNX copies are used.
    for f in list(out_dir.rglob("*")):
        if f.is_file() and f.name.lower().endswith(FORBIDDEN_SUFFIXES):
            f.unlink()


def main(argv: list[str]) -> int:
    out_dir, manifest = Path(argv[1]), Path(argv[2])
    fetch(out_dir)
    verify_models(out_dir, manifest.read_text(encoding="utf-8"))
    print(f"Docling models verified in {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
