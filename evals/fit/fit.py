"""Model fit test bench and worker promotion decision rule."""

import argparse
import asyncio
import datetime
import json
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel


class FitResult(BaseModel):
    """Result of running a fit measurement on a model tag."""

    tag: str
    size_bytes: int
    size_vram_bytes: int
    fit: Literal["fits", "split", "mostly_ram"]
    tokens_per_s: float


def classify_fit(size: int, size_vram: int) -> Literal["fits", "split", "mostly_ram"]:
    """Classify model VRAM allocation into fits, split, or mostly_ram."""
    if size <= 0:
        return "mostly_ram"
    ratio = size_vram / size
    if ratio >= 0.99:
        return "fits"
    if ratio >= 0.50:
        return "split"
    return "mostly_ram"


def ps_sizes(ps_json: dict[str, Any], tag: str) -> tuple[int, int]:
    """Find model matching tag in ps response and return (size, size_vram)."""
    for model in ps_json.get("models", []):
        if model.get("name") == tag or model.get("model") == tag:
            return int(model.get("size", 0)), int(model.get("size_vram", 0))
    return (0, 0)


def choose_worker(results: dict[str, FitResult]) -> tuple[str, str]:
    """Choose (worker, checker) based on whether E4B fits and runs >= 20 tps."""
    e4b = results.get("gemma4:e4b-it-qat")
    if e4b is not None and e4b.fit == "fits" and e4b.tokens_per_s >= 20.0:
        return ("gemma4:e4b-it-qat", "qwen3.5:4b")
    return ("qwen3.5:4b", "gemma4:e2b-it-qat")


async def measure(
    tag: str,
    base_url: str,
    *,
    prompt_tokens: int = 2000,
    gen_tokens: int = 256,
) -> FitResult:
    """Measure inference throughput and VRAM placement of an Ollama model."""
    url = base_url.rstrip("/")
    prompt = " ".join(["filler"] * prompt_tokens)
    payload = {
        "model": tag,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 8192,
            "num_predict": gen_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        gen_resp = await client.post(f"{url}/api/generate", json=payload)
        gen_resp.raise_for_status()
        gen_data = gen_resp.json()

        eval_count = int(gen_data.get("eval_count", 0))
        eval_duration = int(gen_data.get("eval_duration", 0))  # nanoseconds
        tokens_per_s = (eval_count / (eval_duration / 1e9)) if eval_duration > 0 else 0.0

        ps_resp = await client.get(f"{url}/api/ps")
        ps_resp.raise_for_status()
        ps_data = ps_resp.json()

    size, size_vram = ps_sizes(ps_data, tag)
    fit = classify_fit(size, size_vram)
    return FitResult(
        tag=tag,
        size_bytes=size,
        size_vram_bytes=size_vram,
        fit=fit,
        tokens_per_s=round(tokens_per_s, 2),
    )


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for fit test."""
    parser = argparse.ArgumentParser(description="Model fit test bench")
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "tags",
        nargs="+",
        help="Model tags to evaluate",
    )
    return parser.parse_args(args)


def save_fit_results(
    results: dict[str, FitResult],
    output_dir: Path | None = None,
) -> Path:
    """Save results map to daily JSON file and print summary table."""
    target_dir = output_dir or (Path(__file__).resolve().parent / "results")
    target_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.date.today().isoformat()
    out_file = target_dir / f"{today_str}.json"

    data = {tag: res.model_dump() for tag, res in results.items()}
    out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"\nSaved results to {out_file}\n")
    print(f"{'Model Tag':<25} {'Size (MB)':<12} {'VRAM (MB)':<12} {'Fit':<12} {'Tokens/s':<10}")
    print("-" * 75)
    for res in results.values():
        size_mb = f"{res.size_bytes / (1024 * 1024):.1f}"
        vram_mb = f"{res.size_vram_bytes / (1024 * 1024):.1f}"
        print(f"{res.tag:<25} {size_mb:<12} {vram_mb:<12} {res.fit:<12} {res.tokens_per_s:<10.1f}")

    worker, checker = choose_worker(results)
    print(f"\nRecommended worker: {worker}")
    print(f"Recommended checker: {checker}\n")
    return out_file


async def run_fit_bench(
    tags: list[str],
    base_url: str,
    output_dir: Path | None = None,
) -> dict[str, FitResult]:
    """Run fit test across tags, save daily JSON results, and return results map."""
    results: dict[str, FitResult] = {}
    for tag in tags:
        print(f"Measuring {tag}...")
        results[tag] = await measure(tag, base_url)

    save_fit_results(results, output_dir)
    return results


def main() -> None:
    """CLI entry point for python -m evals.fit.fit."""
    args = parse_args()
    asyncio.run(run_fit_bench(args.tags, args.base_url))


if __name__ == "__main__":
    main()
