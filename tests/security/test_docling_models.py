"""Docling's offline models: pinned by content, no pickle files (SEC-23).

Approved by the owner on 2026-11-13: layout (docling-layout-heron),
TableFormer (docling-models) and RapidOCR, baked into the parser image.
"""

import hashlib
from pathlib import Path

import pytest

from scripts.fetch_docling_models import FORBIDDEN_SUFFIXES, verify_models

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "infra/models/docling_models.sha256"


def write_tree(base: Path, files: dict[str, bytes]) -> str:
    lines = []
    for rel, data in files.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")
    return "\n".join(lines) + "\n"


def test_manifest_has_no_pickle_files_and_the_three_models():
    names = [ln.split("  ", 1)[1] for ln in MANIFEST.read_text().splitlines() if ln.strip()]
    assert not [n for n in names if n.endswith(FORBIDDEN_SUFFIXES)]
    assert any(n.endswith("docling-layout-heron/model.safetensors") for n in names)
    assert any(n.endswith("tableformer_accurate.safetensors") for n in names)
    assert any(n.startswith("RapidOcr/") and n.endswith(".onnx") for n in names)


def test_matching_tree_passes(tmp_path):
    manifest = write_tree(tmp_path, {"a/model.safetensors": b"x", "RapidOcr/m.onnx": b"y"})
    verify_models(tmp_path, manifest)


def test_changed_file_fails(tmp_path):
    manifest = write_tree(tmp_path, {"a/model.safetensors": b"x"})
    (tmp_path / "a/model.safetensors").write_bytes(b"changed upstream")
    with pytest.raises(ValueError, match="hash"):
        verify_models(tmp_path, manifest)


def test_extra_or_missing_file_fails(tmp_path):
    manifest = write_tree(tmp_path, {"a/model.safetensors": b"x"})
    (tmp_path / "a/new.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="not in the manifest"):
        verify_models(tmp_path, manifest)
    (tmp_path / "a/new.json").unlink()
    (tmp_path / "a/model.safetensors").unlink()
    with pytest.raises(ValueError, match="missing"):
        verify_models(tmp_path, manifest)


@pytest.mark.parametrize("name", ["RapidOcr/m.pth", "x/model.pt", "x/model.pkl", "x/w.bin"])
def test_pickle_type_file_fails_even_if_listed(tmp_path, name):
    manifest = write_tree(tmp_path, {name: b"x"})
    with pytest.raises(ValueError, match="forbidden"):
        verify_models(tmp_path, manifest)


def test_parser_image_uses_the_verified_models_offline():
    text = (ROOT / "infra/docker/Dockerfile").read_text()
    parser = text[text.index("FROM runtime AS parser") :]
    assert "TR_DOCLING_ARTIFACTS=/opt/models/docling" in parser
    assert "HF_HUB_OFFLINE=1" in parser
    assert "COPY --from=docling-models" in parser
    assert "scripts/fetch_docling_models.py" in text
