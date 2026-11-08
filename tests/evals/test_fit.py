from pathlib import Path

import pytest
import respx

from evals.fit.fit import (
    FitResult,
    choose_worker,
    classify_fit,
    measure,
    parse_args,
    ps_sizes,
    run_fit_bench,
)


def test_classify_fit_thresholds() -> None:
    assert classify_fit(100, 100) == "fits"
    assert classify_fit(100, 60) == "split"
    assert classify_fit(100, 10) == "mostly_ram"
    assert classify_fit(0, 0) == "mostly_ram"


def test_ps_sizes_reads_fixture() -> None:
    ps = {"models": [{"name": "qwen3.5:4b", "size": 4_000, "size_vram": 4_000}]}
    assert ps_sizes(ps, "qwen3.5:4b") == (4_000, 4_000)
    assert ps_sizes(ps, "missing:model") == (0, 0)
    assert ps_sizes({}, "qwen3.5:4b") == (0, 0)


def test_choose_worker_promotes_e4b_only_when_fast_and_fits() -> None:
    r = lambda fit, tps: FitResult(  # noqa: E731
        tag="gemma4:e4b-it-qat",
        size_bytes=1,
        size_vram_bytes=1,
        fit=fit,
        tokens_per_s=tps,
    )
    assert choose_worker({"gemma4:e4b-it-qat": r("fits", 25.0)}) == (
        "gemma4:e4b-it-qat",
        "qwen3.5:4b",
    )
    assert choose_worker({"gemma4:e4b-it-qat": r("split", 25.0)}) == (
        "qwen3.5:4b",
        "gemma4:e2b-it-qat",
    )
    assert choose_worker({"gemma4:e4b-it-qat": r("fits", 12.0)}) == (
        "qwen3.5:4b",
        "gemma4:e2b-it-qat",
    )
    assert choose_worker({}) == ("qwen3.5:4b", "gemma4:e2b-it-qat")


@pytest.mark.asyncio
@respx.mock
async def test_measure_computes_tps_and_fit() -> None:
    base_url = "http://fake-ollama:11434"
    respx.post(f"{base_url}/api/generate").respond(
        status_code=200,
        json={
            "eval_count": 250,
            "eval_duration": 10_000_000_000,  # 10s -> 25 tokens/s
        },
    )
    respx.get(f"{base_url}/api/ps").respond(
        status_code=200,
        json={
            "models": [
                {
                    "name": "gemma4:e4b-it-qat",
                    "size": 6_000_000_000,
                    "size_vram": 6_000_000_000,
                }
            ]
        },
    )
    res = await measure("gemma4:e4b-it-qat", base_url, prompt_tokens=10, gen_tokens=20)
    assert res.tag == "gemma4:e4b-it-qat"
    assert res.tokens_per_s == pytest.approx(25.0)
    assert res.fit == "fits"
    assert res.size_bytes == 6_000_000_000
    assert res.size_vram_bytes == 6_000_000_000


def test_parse_args_defaults_and_tags() -> None:
    args = parse_args(["qwen3.5:4b", "gemma4:e2b-it-qat"])
    assert args.base_url == "http://localhost:11434"
    assert args.tags == ["qwen3.5:4b", "gemma4:e2b-it-qat"]

    custom = parse_args(["--base-url", "http://ollama:11434", "bge-m3"])
    assert custom.base_url == "http://ollama:11434"
    assert custom.tags == ["bge-m3"]


def _verify_output_files(target_dir: Path) -> None:
    json_files = list(target_dir.glob("*.json"))
    assert len(json_files) == 1
    content = json_files[0].read_text(encoding="utf-8")
    assert "qwen3.5:4b" in content
    assert '"fit": "fits"' in content


@pytest.mark.asyncio
@respx.mock
async def test_run_fit_bench_writes_daily_file(tmp_path: Path) -> None:
    base_url = "http://fake-ollama:11434"
    respx.post(f"{base_url}/api/generate").respond(
        status_code=200,
        json={"eval_count": 200, "eval_duration": 10_000_000_000},
    )
    respx.get(f"{base_url}/api/ps").respond(
        status_code=200,
        json={
            "models": [
                {
                    "name": "qwen3.5:4b",
                    "size": 4_000_000_000,
                    "size_vram": 4_000_000_000,
                }
            ]
        },
    )
    results = await run_fit_bench(["qwen3.5:4b"], base_url, output_dir=tmp_path)
    assert "qwen3.5:4b" in results
    assert results["qwen3.5:4b"].fit == "fits"
    _verify_output_files(tmp_path)
