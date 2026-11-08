"""Tests for ModelsAdmin and VRAM fit estimation."""

from pathlib import Path

import pytest

from techradar.llm.admin import ModelsAdmin, ModelSpec


def test_list_configured_models_reads_repo_file() -> None:
    specs = ModelsAdmin.list_configured_models()
    assert len(specs) >= 5

    role_map = {s.role: s for s in specs}
    assert set(role_map.keys()) >= {"worker", "checker", "night", "embed", "vision"}

    worker = role_map["worker"]
    assert isinstance(worker, ModelSpec)
    assert worker.name == "qwen3.5:4b"
    assert worker.family == "qwen"
    assert worker.context_limit == 8192
    assert worker.vram_gb == pytest.approx(3.3, abs=0.1)
    assert worker.quant == "q4_k_m"

    checker = role_map["checker"]
    assert checker.name == "gemma4:e2b-it-qat"
    assert checker.family == "gemma"
    assert checker.quant == "qat"
    assert checker.vram_gb == pytest.approx(4.3, abs=0.1)

    night = role_map["night"]
    assert night.name == "gemma4:12b-it-qat"
    assert night.vram_gb == pytest.approx(7.2, abs=0.1)


def test_list_configured_models_custom_yaml(tmp_path: Path) -> None:
    yaml_content = (
        'custom_worker: {ollama_tag: "mistral:7b", family: mistral, '
        'num_ctx: 4096, vram_gb: 5.5, quant: "q8_0"}\n'
    )
    cfg_file = tmp_path / "custom_roles.yaml"
    cfg_file.write_text(yaml_content, encoding="utf-8")

    specs = ModelsAdmin.list_configured_models(cfg_file)
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "mistral:7b"
    assert spec.family == "mistral"
    assert spec.context_limit == 4096
    assert spec.vram_gb == 5.5
    assert spec.quant == "q8_0"
    assert spec.role == "custom_worker"


def test_estimate_vram_fit_within_budget() -> None:
    # 6GB GPU running only worker (3.3 GB) fits comfortably
    fit = ModelsAdmin.estimate_vram_fit(total_vram_gb=6.0, model_names=["qwen3.5:4b"])
    assert fit["fits"] is True
    assert fit["overflow"] is False
    assert fit["overflow_gb"] == 0.0
    assert fit["required_vram_gb"] == pytest.approx(3.3, abs=0.1)
    assert fit["remaining_vram_gb"] == pytest.approx(2.7, abs=0.1)


def test_estimate_vram_fit_accurately_flags_overflow() -> None:
    # 6GB GPU running worker (3.3 GB) + checker (4.3 GB) = 7.6 GB -> overflows budget by 1.6 GB
    fit = ModelsAdmin.estimate_vram_fit(
        total_vram_gb=6.0,
        model_names=["qwen3.5:4b", "gemma4:e2b-it-qat"],
    )
    assert fit["fits"] is False
    assert fit["overflow"] is True
    assert fit["required_vram_gb"] == pytest.approx(7.6, abs=0.1)
    assert fit["overflow_gb"] == pytest.approx(1.6, abs=0.1)
    assert fit["remaining_vram_gb"] == 0.0


def test_estimate_vram_fit_apple_silicon_unified_memory() -> None:
    # 16GB Unified Memory running worker (3.3) + checker (4.3) + embed (1.2) = 8.8 GB fits
    fit = ModelsAdmin.estimate_vram_fit(
        total_vram_gb=16.0,
        model_names=["qwen3.5:4b", "gemma4:e2b-it-qat", "bge-m3"],
    )
    assert fit["fits"] is True
    assert fit["overflow"] is False
    assert fit["required_vram_gb"] == pytest.approx(8.8, abs=0.1)
    assert fit["remaining_vram_gb"] == pytest.approx(7.2, abs=0.1)


def test_estimate_vram_fit_by_role_names() -> None:
    # Worker (3.3) + Embed (1.2) = 4.5 GB fits in 6GB
    fit_ok = ModelsAdmin.estimate_vram_fit(total_vram_gb=6.0, model_names=["worker", "embed"])
    assert fit_ok["fits"] is True
    assert fit_ok["overflow"] is False

    # Worker (3.3) + Night (7.2) = 10.5 GB overflows 6GB
    fit_overflow = ModelsAdmin.estimate_vram_fit(
        total_vram_gb=6.0,
        model_names=["worker", "night"],
    )
    assert fit_overflow["fits"] is False
    assert fit_overflow["overflow"] is True
    assert fit_overflow["overflow_gb"] == pytest.approx(4.5, abs=0.1)


def test_models_admin_instance_and_class_access() -> None:
    admin = ModelsAdmin()
    specs_from_instance = admin.list_configured_models()
    specs_from_class = ModelsAdmin.list_configured_models()
    assert len(specs_from_instance) == len(specs_from_class)

    fit_instance = admin.estimate_vram_fit(8.0, ["worker"])
    fit_class = ModelsAdmin.estimate_vram_fit(8.0, ["worker"])
    assert fit_instance["fits"] == fit_class["fits"]
