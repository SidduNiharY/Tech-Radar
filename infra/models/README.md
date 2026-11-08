# Model Lineup & Fit Test Bench

This directory documents the local LLM model lineup for TechRadar Brain, VRAM placement expectations, pulling instructions, and the fit test benchmarking process.

## 1. Model Lineup & Roles

All models are served locally via Ollama (`http://ollama:11434` in Docker, or `http://localhost:11434` for local dev).

| Role | Default Model Tag | Family | Size (Disk/RAM) | Context (`num_ctx`) | Purpose |
|---|---|---|---|---|---|
| **Worker** | `qwen3.5:4b` | `qwen` | 3.3–4.0 GB | 8192 | Primary interactive agent, task execution, extraction |
| **Checker** | `gemma4:e2b-it-qat` | `gemma` | 4.3 GB | 8192 | Verification, safety checks, cross-model critique |
| **Night** | `gemma4:12b-it-qat` | `gemma` | 7.2 GB | 8192 | Offline night batch processing, knowledge distillation |
| **Embed** | `bge-m3` | `bge` | 1.2 GB | 8192 | Hybrid/dense vector embeddings for RAG indexing |
| **Vision** | `qwen3.5:4b` | `qwen` | 3.3–4.0 GB | 8192 | Multimodal diagram, slide, and image understanding |
| **Test (Worker Candidate)** | `gemma4:e4b-it-qat` | `gemma` | 6.1 GB | 8192 | Candidate for worker promotion if fit and throughput qualify |

### Model Family Diversity Rule (Decision D6)
The worker and checker **must** originate from different model families (e.g. Qwen vs Gemma) to prevent correlated failure modes and shared model hallucinations during verification.

---

## 2. Security & Provenance (SEC-23)
- Models are sourced **exclusively** from the official Ollama library.
- Direct downloads of arbitrary pickle files or `torch.load` from unvetted sources are forbidden.
- Models are pulled via the isolated `ollama-pull` profile container which routes through the Squid egress proxy allowlist (`registry.ollama.ai`).

---

## 3. Pulling Models (Operator Instructions)

Because models are large and the Ollama server needs exclusive write access to the volume during pull, pull models one at a time using the one-off `ollama-pull` service:

```bash
# 1. Stop ollama service to release storage lock
docker compose stop ollama

# 2. Pull models one at a time
docker compose --profile pull run --rm -e MODEL=qwen3.5:4b ollama-pull
docker compose --profile pull run --rm -e MODEL=gemma4:e2b-it-qat ollama-pull
docker compose --profile pull run --rm -e MODEL=gemma4:12b-it-qat ollama-pull
docker compose --profile pull run --rm -e MODEL=bge-m3 ollama-pull
docker compose --profile pull run --rm -e MODEL=gemma4:e4b-it-qat ollama-pull

# 3. Restart ollama server
docker compose start ollama
```

---

## 4. VRAM Fit Categories & Classification

The fit test bench queries Ollama's `/api/ps` endpoint to inspect model size and VRAM allocation (`size` and `size_vram`):

$$\text{ratio} = \frac{\text{size\_vram}}{\text{size}}$$

| Category | Ratio | Meaning | Action / Viability |
|---|---|---|---|
| `fits` | $\ge 0.99$ | Entire model weights fit directly in GPU VRAM | Optimal latency, acceptable for interactive worker |
| `split` | $0.50 \le \text{ratio} < 0.99$ | Weights split across VRAM and host RAM | Suboptimal latency; usable for checker or background jobs |
| `mostly_ram` | $< 0.50$ | Execution largely driven by host CPU / RAM | High latency; only acceptable for non-interactive night jobs |

---

## 5. Worker Promotion Decision Rule

The fit test bench implements `choose_worker(results)` in `evals.fit.fit`:

1. Checks if `gemma4:e4b-it-qat` is evaluated.
2. If `gemma4:e4b-it-qat` achieves `fit == "fits"` **and** inference throughput $\ge 20.0$ tokens/second:
   - Worker promoted to `gemma4:e4b-it-qat`
   - Checker becomes `qwen3.5:4b` (preserving the model family diversity rule)
   - Update `infra/models/roles.yaml` accordingly.
3. Otherwise (if E4B does not fit or runs $< 20.0$ tokens/s):
   - Worker remains `qwen3.5:4b`
   - Checker remains `gemma4:e2b-it-qat`

---

## 6. Running the Fit Test Bench

### Local CLI:
```bash
python -m evals.fit.fit --base-url http://localhost:11434 qwen3.5:4b gemma4:e2b-it-qat gemma4:12b-it-qat gemma4:e4b-it-qat
```

### In Docker:
```bash
docker compose --profile test run --rm evals python -m evals.fit.fit \
    --base-url http://ollama:11434 \
    qwen3.5:4b gemma4:e2b-it-qat gemma4:12b-it-qat gemma4:e4b-it-qat
```

### Outputs:
- Results are saved to `evals/fit/results/<YYYY-MM-DD>.json`.
- A formatted performance table is printed with:
  - Model Tag
  - Size (MB)
  - VRAM (MB)
  - Fit Classification (`fits`, `split`, `mostly_ram`)
  - Inference Throughput (tokens/s)
  - Recommended Worker and Checker
