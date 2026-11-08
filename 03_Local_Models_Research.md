# TechRadar Brain: Local Models Research

**As of 2026-11-07.** Companion to [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md), section 5.4. Research only: no model was downloaded or run, so every speed and fit statement below is either copied from a primary source or marked as an estimate.

## Summary

- Most of the current plan holds up: Gemma 4 12B, Qwen 3.5 4B, BGE-M3, bge-reranker-v2-m3, Whisper large-v3-turbo, Kokoro and the wav2vec2 phoneme model are all still good, permissively licensed picks (Apache 2.0 or MIT) as of this date.
- **Biggest surprise: Gemma 4 E4B does not fit 6 GB VRAM in Ollama.** The Q4_K_M file is 6.6 GB (the "E" models store 8B parameters, 4.5B of them effective). It is also over the Mac's 4-6 GB budget. The Gemma 4 E2B (4.6 GB) or Qwen3.5-4B (about 3.3 GB) fit; the E4B needs a real fit test first (the 5.15 GB official QAT GGUF in llama.cpp is the best chance).
- **gpt-oss 20B is not realistic on 16 GB RAM** (12-14 GB file vs 6 GB VRAM + 6-8 GB free RAM). After a 32 GB upgrade, Gemma 4 26B A4B (3.8B active) is the better night writer.
- Two things the cards do not promise: **fillers (um, uh) in Whisper output**, and **Hindi/Telugu speech quality**. Both need your own tests. For Hindi and Telugu text search, Granite Embedding R2 311M is the only candidate whose card names both languages (BGE-M3's MIRACL training set includes both).
- Qwen3.5-4B can also be the vision model for handwriting and maths, so one model covers two roles.

## Recommended lineup

| # | Role | Pick | Backup | Machine | 4-bit memory | Licence | Why |
|---|---|---|---|---|---|---|---|
| 1 | Daily worker | Gemma 4 E4B (only if the fit test passes; run the 5.15 GB QAT GGUF in llama.cpp) | Gemma 4 E2B (also the Mac choice) or Qwen3.5-4B with thinking off | Server GPU; Mac gets E2B | E4B 5.2-6.6 GB (too big); E2B 4.3-4.6 GB; Qwen3.5-4B about 3.3 GB | Apache 2.0 | Best quality that has a chance of fitting; Google's own structured tool-use support |
| 2 | Checker | Qwen3.5-4B | Granite 4.2 3B (2.2 GB) or Nemotron 3 Nano 4B (2.84 GB) | Server GPU | about 3.3 GB | Apache 2.0 (Nemotron: NVIDIA Open Model License) | Different family from Gemma; IFEval 89.8 on its card |
| 3 | Night writer | Gemma 4 12B (QAT or Q4_K_M) | Qwen3.5-9B; after 32 GB RAM: Gemma 4 26B A4B | Server GPU + RAM | 7.0-8.0 GB (GPU 5 GB + RAM 2-3 GB) | Apache 2.0 | Largest strong dense model that fits the split budget; gpt-oss 20B dropped for now |
| 4 | Embeddings | BGE-M3 | Granite Embedding 311M Multilingual R2; Harrier-OSS-v1 0.6B | Server GPU or CPU; Mac | 1.2 GB (FP16) | MIT (Granite: Apache 2.0, Harrier: MIT) | 8K context, proven; Granite names Hindi and Telugu |
| 5 | Reranker | bge-reranker-v2-m3 | Qwen3-Reranker-0.6B | Server GPU or CPU | about 1.2 GB FP16 (estimate) | Apache 2.0 | Same base as BGE-M3; Qwen reranker has published scores |
| 6 | Speech-to-text | Whisper large-v3-turbo (faster-whisper; mlx-whisper on Mac) | Whisper large-v3 for scored sessions; Parakeet-TDT-0.6B-v3 for English-only live mode | Server GPU; Mac | 1.61 GB MLX; about 2-3 GB int8 (estimate) | MIT (Parakeet: CC-BY-4.0) | Only candidate with word timestamps, Hindi and Telugu in its language list and an Apple build |
| 7 | Text-to-speech | Kokoro-82M | Indic Parler-TTS (Indian English, Hindi, Telugu) | Any, CPU is fine | about 0.3 GB (80 MB quantized) | Apache 2.0 | Tiny and fast; no Indian-English voice in Kokoro, so Parler is the bonus option |
| 8 | Phoneme recognition | wav2vec2-lv-60-espeak-cv-ft | POWSM CTC (espnet) | Server GPU; Mac | about 1.2 GB FP32 (estimate) | Apache 2.0 (POWSM: CC-BY-4.0) | Plain Transformers; POWSM is newer with a forced-alignment script |
| 9 | Vision / OCR | RapidOCR via Docling for print; Qwen3.5-4B for handwriting and maths | Granite-Docling-258M; PaddleOCR-VL-1.6 | Server (CPU for OCR; GPU for VLM); Mac | VLM about 3.3 GB; Granite-Docling about 0.5 GB | Apache 2.0 / MIT | Reuses the checker model; check maths with SymPy |



## How to read the tables

- **4-bit memory** = the size of the Q4-class file that Ollama or the GGUF publisher lists (this is the real number that has to fit), plus KV cache (the memory the context uses; grows with the 8k context). The rule of thumb "Q4_K_M is about 0.6 GB per billion parameters" is used only when no file size was found.
- **Fits 6 GB VRAM?** A model file bigger than about 5 GB does not fit the RTX 3060 comfortably, because the context cache, CUDA buffers and the desktop also use VRAM.
- **"not stated"** means the primary source does not say. **(unverified)** means only a secondary source (news, blog, aggregator) said it.
- Sizes from Ollama pages are copied from the Ollama library tag pages (ollama.com/library/...). Ollama tags can change; re-check before pulling.
- Release dates are exact only when a model card or official page gives one. Hugging Face (HF) cards often give only a paper date or a citation year.

---

## Role 1. Daily worker LLM (tags, short summaries, JSON facts, MCQ wording)

Needs: fits fully in 6 GB VRAM at 4-bit with 8k context, reliable JSON.

| Candidate | HF repo | Params (total / active) | Released | Licence | Context | Formats (who publishes GGUF) | Ollama tag and size | 4-bit memory and fit |
|---|---|---|---|---|---|---|---|---|
| **Gemma 4 E4B** (current pick) | [google/gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) | 4.5B effective / 8B with per-layer embeddings; dense, not MoE | HF card: not stated (tech report "Jul 2", 2026). News says 2026-04-02 (unverified, secondary: [aimlapi blog](https://aimlapi.com/blog/gemma-4---google-deepminds-most-powerful-open-weight-ai-model-family)) | Apache 2.0, no extra restriction stated on the card | 128K | safetensors (Google). Official GGUF: [google/gemma-4-E4B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf) (5.15 GB, QAT Q4_0). Others: unsloth, ggml-org, bartowski, lmstudio-community ([search](https://huggingface.co/models?search=gemma-4-E4B-it-GGUF&sort=downloads)). MLX in Ollama only | `gemma4:e4b-it-q4_K_M` 6.6 GB; `gemma4:e4b-it-qat` 6.1 GB; default `gemma4:e4b` 6.6-9.5 GB ([Ollama tags](https://ollama.com/library/gemma4/tags)) | Google's own table: 4.5 GB for Q4_0 weights, excluding KV cache ([Gemma docs](https://ai.google.dev/gemma/docs/core)). Ollama file is 6.6 GB. **Does NOT fit 6 GB VRAM cleanly in Ollama**: expect a partial CPU split. The 5.15 GB QAT GGUF in llama.cpp is the best chance (see test plan) |
| **Gemma 4 E2B** (fallback) | [google/gemma-4-E2B-it](https://huggingface.co/google/gemma-4-E2B-it) | 2.3B effective / 5.1B with embeddings | same family as above | Apache 2.0 | 128K | safetensors; GGUF by third parties; Ollama MLX tag | `gemma4:e2b-it-q4_K_M` 4.6 GB; `gemma4:e2b-it-qat` 4.3 GB | Google table: 2.9 GB Q4_0. Ollama file 4.6 GB: **fits 6 GB** with 8k context |
| **Qwen3.5-4B** | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | 4B (5B in safetensors metadata, includes vision encoder); hybrid Gated DeltaNet + attention | HF card: Feb 2026 (citation year/month only) | Apache 2.0 | 262,144 native | safetensors (Qwen). No GGUF under the Qwen org in the search; unsloth, lmstudio-community, bartowski publish it ([search](https://huggingface.co/models?search=Qwen3.5-4B-GGUF&sort=downloads)) | `qwen3.5:4b` 3.3-4.0 GB ([Ollama](https://ollama.com/library/qwen3.5)) | about 3.3 GB: **fits 6 GB** with room for a big KV cache |
| **Granite 4.2 3B** | [ibm-granite/granite-4.2-3b](https://huggingface.co/ibm-granite/granite-4.2-3b) | 3B (4B in metadata); dense decoder | 2026-08-25 (HF card) | Apache 2.0 | 128K native | safetensors; official GGUF [ibm-granite/granite-4.2-3b-GGUF](https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF) (namespace is IBM's; the page does not label it "official") | `granite4.2:3b` 2.2 GB ([Ollama](https://ollama.com/library/granite4.2)) | 2.2 GB: **fits easily** |
| **Nemotron 3 Nano 4B** (NVIDIA) | [nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16) | 3.97B; Mamba-2/Transformer hybrid (only 4 attention layers) | 2026-03-16 (HF card) | NVIDIA Nemotron Open Model License (not Apache; card says "ready for commercial use"; read the agreement before redistributing) | up to 262K | safetensors; official GGUF [nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF), Q4_K_M 2.84 GB | Ollama tag: not checked | 2.84 GB: **fits easily**. Small KV cache because few attention layers (architecture fact from the card; exact saving not stated) |
| **Granite 4.2 8B** | [ibm-granite/granite-4.2-8b](https://huggingface.co/ibm-granite/granite-4.2-8b) | 8B (9B in metadata) | HF listing: about Oct 2026 ("18 days ago" on [org page](https://huggingface.co/ibm-granite)) (approximate) | Apache 2.0 | 128K | as above | `granite4.2:8b` 5.3 GB | 5.3 GB file: **borderline**; likely a few layers on CPU at 8k context |

Quality notes (model cards only):
- Gemma 4 E4B: MMLU-Pro 69.4, GPQA Diamond 58.6, MMMLU 76.6; the card says it has "native support for structured tool use" and "native function-calling support" but does not mention JSON output specifically ([E4B card](https://huggingface.co/google/gemma-4-E4B-it)). E2B: MMLU-Pro 60.0, IFBench 38 ([E2B card](https://huggingface.co/google/gemma-4-E2B-it)).
- Qwen3.5-4B: IFEval 89.8, IFBench 59.2, MMLU-Pro 79.1, no JSON benchmark ([card](https://huggingface.co/Qwen/Qwen3.5-4B)). Thinking is on by default (it prints a `<think>` block first); turn it off with `chat_template_kwargs: {"enable_thinking": false}`. It does not support the `/think` and `/nothink` switches. This matters for JSON jobs: a long thinking block wastes tokens and can break parsers.
- Nemotron 3 Nano 4B: IFEval prompt-level 82.8 (reasoning off) / 87.9 (on), IFBench 43.2, BFCL v3 function calling 61.1, RULER 128k 91.1; English only; reasoning is on by default and can be switched off; no JSON benchmark ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16)).
- Granite 4.2 3B: BFCL v4 (function calling) 52.41, no IFEval and no JSON benchmark reported ([card](https://huggingface.co/ibm-granite/granite-4.2-3b)). Languages: English, German, Spanish, French, Japanese, Portuguese, Arabic, Czech, Italian, Korean, Dutch, Chinese (no Hindi or Telugu).
- Languages: Gemma 4 is "pre-trained on 140+ languages, 35+ out of the box"; Qwen3.5 says 201 languages and dialects.

Trade-offs:
- **Surprise: the current pick does not fit 6 GB in Ollama.** The Ollama Q4_K_M file for Gemma 4 E4B is 6.6 GB because the "E" models carry large per-layer embedding tables (8B stored, 4.5B effective). Whether those tables can stay in system RAM without slowing generation is not stated in the model card. Test before trusting.
- **Safest swap if it spills:** Gemma 4 E2B (4.6 GB) or Qwen3.5-4B (about 3.3 GB). Qwen3.5-4B scores higher than Gemma 4 E4B on the numbers each card reports (MMLU-Pro 79.1 vs 69.4), but the benchmarks are not the same test settings, so treat this as a hint only.
- If the worker is Qwen3.5-4B, the checker must be a different family (Gemma or Granite), so the "two families" rule from the stack file still holds. Roles 1 and 2 can simply swap.
- Granite 4.2 3B is the smallest and has the cleanest licence story (Apache 2.0, IBM), but it reports no instruction-following score, so it needs your own test set.

---

## Role 2. Checker LLM (different family from the worker; cross-checks facts and MCQ answers)

Needs: fits 6 GB (it may share the GPU in turns, since only one model is loaded at a time); different family from the worker.

| Candidate | HF repo | Params | Released | Licence | Context | Formats / GGUF | Ollama tag and size | 4-bit memory and fit |
|---|---|---|---|---|---|---|---|---|
| **Qwen3.5-4B** (best pick if the worker is Gemma) | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | 4B | Feb 2026 (HF card) | Apache 2.0 | 262,144 | see Role 1 | `qwen3.5:4b` 3.3-4.0 GB | about 3.3 GB: **fits** |
| **Qwen3.5-2B** | [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) | 2B | Feb 2026 | Apache 2.0 | 262,144 | see Role 1 | `qwen3.5:2b` 2.7-3.1 GB | about 2.7 GB: **fits**. Card warns the 2B is more prone to thinking loops |
| **Granite 4.2 3B** | [ibm-granite/granite-4.2-3b](https://huggingface.co/ibm-granite/granite-4.2-3b) | 3B | 2026-08-25 | Apache 2.0 | 128K | official GGUF in `ibm-granite` namespace | `granite4.2:3b` 2.2 GB | 2.2 GB: **fits** |
| **Nemotron 3 Nano 4B** | [nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16) | 3.97B (hybrid) | 2026-03-16 | NVIDIA Nemotron Open Model License | up to 262K | official GGUF Q4_K_M 2.84 GB | Ollama tag: not checked | 2.84 GB: **fits**. Third model family (NVIDIA), English only. Good tie-breaker voter |
| **Ministral 3 8B Instruct** | [mistralai/Ministral-3-8B-Instruct-2512](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512) | 8.4B + 0.4B vision encoder | paper listed 2026-01-13 (card gives no release date) | Apache 2.0 | 256K | FP8 weights on the card; GGUF not mentioned on card | Ollama tag and size: not checked | card says "fits in 12GB VRAM in FP8"; at 4-bit about 5 GB by the 0.6 GB/B rule: borderline |

Quality notes (model cards only):
- Qwen3.5-4B: IFEval 89.8, MMLU-Pro 79.1, GPQA Diamond 76.2 ([card](https://huggingface.co/Qwen/Qwen3.5-4B)). Qwen3.5-2B: IFEval 61.2 non-thinking / 78.6 thinking, MMLU-Pro 55.3 / 66.5 ([card](https://huggingface.co/Qwen/Qwen3.5-2B)).
- Ministral 3 8B: native function calling and JSON output, 11 languages, Apache 2.0 ([card](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512)).
- Granite 4.2 3B: see Role 1.

Trade-offs:
- **Confirm the current pick** (small Qwen 3.5): pick the **4B**, not the 2B. The 2B drops sharply on IFEval in non-thinking mode (61.2 vs 78.6 in thinking).
- A checker should run with thinking **on** when checking an MCQ (the extra reasoning helps), but with a hard token cap, because thinking loops are a documented risk on small Qwen3.5 models.
- Do not use the same family as the worker. If you change the worker to Qwen3.5-4B, the checker becomes Gemma 4 E2B or Granite 4.2 3B.
- A good use of Granite 4.2 3B is as a third voter when the worker and checker disagree (cheap: 2.2 GB).

---

## Role 3. Night writer (deep dives, explanations; slow is fine; 6 GB VRAM + 6-8 GB free RAM)

Budget: the model file plus KV cache should be under about 11-12 GB total (5 GB on the GPU + 6-7 GB in RAM) so the Linux system and Docker still have room.

| Candidate | HF repo | Params (total / active) | Released | Licence | Context | Formats / GGUF | Ollama tag and size | 4-bit memory and fit |
|---|---|---|---|---|---|---|---|---|
| **Gemma 4 12B** (current pick) | [google/gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) | 11.95B dense (all active); text + image + audio in | HF card: not stated (tech report arXiv 2607.02770, "Jul 2", 2026) | Apache 2.0 | 256K | safetensors; official GGUF [google/gemma-4-12B-it-qat-q4_0-gguf](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) (6.98 GB, QAT Q4_0); unsloth, ggml-org, bartowski, lmstudio-community also publish ([search](https://huggingface.co/models?search=gemma-4-12b-it-GGUF&sort=downloads)) | `gemma4:12b-it-q4_K_M` 8.0 GB; `gemma4:12b-it-qat` 7.2 GB ([tags](https://ollama.com/library/gemma4/tags)) | 7-8 GB file: **needs offload**, about 5 GB on GPU and 2-3 GB in RAM. Fits the budget. Dense, so every token reads all weights: expect slow but steady speed (speed not measured) |
| **Qwen3.5-9B** | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | 9B dense (10B in metadata, includes vision) | Feb 2026 (citation) | Apache 2.0 | 262,144 | safetensors; GGUF by third parties (unsloth etc.) | `qwen3.5:9b` 6.6-7.6 GB ([Ollama](https://ollama.com/library/qwen3.5)) | 6.6 GB file: **small offload**, faster than 12B |
| **Ministral 3 14B** | [mistralai/Ministral-3-14B-Instruct-2512](https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512) (card not read) | 14B | collection listed on [Mistral HF org](https://huggingface.co/mistralai); exact date not stated | Apache 2.0 (the 8B card says Apache 2.0; 14B card not read) | 256K | not checked | `ministral-3:14b` 9.1 GB ([Ollama](https://ollama.com/library/ministral-3)) | 9.1 GB: **needs offload**, fits the budget tightly |
| **gpt-oss-20b** (test-first) | [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) | 21B total / 3.6B active (MoE, MXFP4) | model card paper Aug 8, 2025 | Apache 2.0 | not stated on the HF card; 128K on Ollama | safetensors (MXFP4 experts); GGUF by [ggml-org](https://huggingface.co/ggml-org/gpt-oss-20b-GGUF) (MXFP4, 12.1 GB) | `gpt-oss:20b` 14 GB ([Ollama](https://ollama.com/library/gpt-oss)) | 12-14 GB file: **does not fit 6 GB VRAM + 6-8 GB RAM comfortably**. OpenAI says it "runs within 16GB of memory". Realistic only with 32 GB RAM |
| **Gemma 4 26B A4B** (needs 32 GB RAM) | [google/gemma-4-26B-A4B-it](https://huggingface.co/google/gemma-4-26B-A4B-it) | 25.2B total / 3.8B active (MoE) | as Gemma 4 | Apache 2.0 | 256K | official QAT Q4_0 GGUF family (12B and E4B confirmed; 26B not checked) | `gemma4:26b-a4b-it-qat` 16 GB; `q4_K_M` 18 GB | Google table: 14.4 GB Q4_0 weights. **Too big for 6 GB + 6-8 GB.** Becomes the best MoE choice after a 32 GB RAM upgrade |
| **LFM2.5-24B-A2B** | [LiquidAI/LFM2.5-24B-A2B](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B) | 24B total / 2.45B active (MoE) | 2026; exact date not stated | tagged `lfm1.0`; terms not stated on the card (check the LFM licence before use) | 131,072 | GGUF repo linked; sizes not stated | not checked | about 14 GB by the 0.6 GB/B rule: **too big** now |

Quality notes (model cards only):
- Gemma 4 12B: MMLU-Pro 77.2, GPQA Diamond 78.8, AIME 2026 77.5, MRCR v2 8-needle 128k 43.4, IFBench 74 ([card](https://huggingface.co/google/gemma-4-12B-it)). Gemma 4 E4B for comparison: MMLU-Pro 69.4, GPQA 58.6.
- Qwen3.5-9B: IFEval 91.5, MMLU-Pro 82.5, GPQA Diamond 81.7; no long-form-writing score on the card ([card](https://huggingface.co/Qwen/Qwen3.5-9B)).
- gpt-oss-20b: GPQA Diamond 66 (medium reasoning), supports low/medium/high reasoning and structured outputs ([card](https://huggingface.co/openai/gpt-oss-20b)).
- Gemma 4 26B A4B: MMLU-Pro 82.6, GPQA Diamond 82.3, AIME 2026 88.3 ([card](https://huggingface.co/google/gemma-4-26B-A4B-it)).
- No source I read gives a writing-quality benchmark for these models, so "which writes better deep dives" must be decided by your own blind test (see test plan).

Trade-offs:
- **Confirm Gemma 4 12B** as the night writer for the current 16 GB RAM. It is the largest strong model that fits the split budget, has a 256K context, and keeps the same family as the worker (fine here: the checker is the different family).
- **gpt-oss 20B is not realistic on 16 GB RAM.** The model file is 12-14 GB, but you only have about 5 GB of VRAM plus 6-8 GB of free RAM. It would swap to disk. The stack file already says "tight"; this research says "no, unless you upgrade RAM".
- **After a 32 GB RAM upgrade** the best night writer is probably Gemma 4 26B A4B (3.8B active parameters, so much faster per token than the dense 12B, and higher card scores). Both it and gpt-oss-20b become runnable then. This supports the "cheap upgrade" line in the stack file.
- **Speed-up for the 12B:** Google publishes [gemma-4-12B-it-assistant](https://huggingface.co/google/gemma-4-12B-it-assistant) (0.4B, Apache 2.0), a multi-token-prediction drafter for speculative decoding; the card claims "up to 3x" faster decoding with identical output, shown with Transformers. The card does not confirm llama.cpp or Ollama support, and the drafter must also fit in memory, so test before relying on it.
- Qwen3.5-9B is the best "faster and probably stronger on paper" alternative; the card numbers (IFEval 91.5, MMLU-Pro 82.5) beat Gemma 4 12B's. But both are labs' own numbers, so run both on your own deep-dive prompts.

---

## Role 4. Multilingual embeddings (strong English; Hindi and Telugu wanted)

All of these are small enough to run on the RTX 3060 *and* the Mac next to a chat model (under about 1.3 GB each). The stack already runs embeddings through sentence-transformers, so Ollama support is a bonus, not a need.

| Candidate | HF repo | Params | Released | Licence | Context | Dims | Formats / GGUF | Ollama tag and size | 4-bit / memory |
|---|---|---|---|---|---|---|---|---|---|
| **BGE-M3** (current pick) | [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | 567M (Ollama page; HF card: not stated) | paper 2024-02-05 | MIT | 8192 | 1024 | sentence-transformers, PyTorch, ONNX; GGUF not on the card (community only) | `bge-m3` 1.2 GB, 8K ([Ollama](https://ollama.com/library/bge-m3)) | 1.2 GB (FP16 file). No 4-bit needed. Fits GPU and Mac |
| **Harrier-OSS-v1 0.6B** | [microsoft/harrier-oss-v1-0.6b](https://huggingface.co/microsoft/harrier-oss-v1-0.6b) | 0.6B (decoder-only) | not stated on card (news: March 2026, unverified: [pulse.bot](https://www.pulse.bot/ai/news/microsoft-ai-releases-harrier-oss-v1-a-new-family-of-multilingual-embedding-models-hitting-sota-on-m-4fe260f0-a338-4356-9ce9-984f7c4c1c9b/)) | MIT | 32,768 | 1024 | safetensors; GGUF and ONNX by community only (e.g. mradermacher, onnx-community) | not found in Ollama (not checked) | about 1.2 GB in BF16 by 2 bytes/param (estimate). Fits |
| **Harrier-OSS-v1 270M** | [microsoft/harrier-oss-v1-270m](https://huggingface.co/microsoft/harrier-oss-v1-270m) | 270M | not stated | MIT | 32,768 | 640 | as above | not checked | about 0.55 GB (estimate). Fits |
| **Granite Embedding 311M Multilingual R2** | [ibm-granite/granite-embedding-311m-multilingual-r2](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2) | 311M (ModernBERT-based) | 2026-04-29 | Apache 2.0 | 32,768 | 768 (Matryoshka to 128) | safetensors, ONNX and OpenVINO by IBM; **Ollama does not support it** (card says so); GGUF needs self-conversion | not available | about 0.6 GB (estimate). Fits |
| **EmbeddingGemma 2** (newest, Google) | [google/embeddinggemma-2](https://huggingface.co/google/embeddinggemma-2) | 740M total (270M text + 170M vision + 300M audio encoders); text-only use needs just the 270M part | card: "published 12 days ago" before 2026-11-07, i.e. about late Oct 2026; HF listing: updated 10 days ago | Apache 2.0 (a change from v1's Gemma terms) | 8192 | 768 (Matryoshka to 128) | safetensors; GGUF/ONNX not named | not checked | under 1.5 GB in BF16 (2 bytes/param estimate). Fits |
| **Qwen3-Embedding-0.6B** | [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 0.6B | paper 2025-06-05 | Apache 2.0 | 32K | up to 1024 (32-1024 selectable) | safetensors; GGUF third-party only | `qwen3-embedding:0.6b` 639 MB, 32K ([Ollama](https://ollama.com/library/qwen3-embedding)) | 0.64 GB. Fits |
| **EmbeddingGemma 300M** | [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m) | 300M | paper 2025-09-24 | "gemma" terms: you must log in and accept Google's usage licence (not Apache 2.0) | 2048 | 768 (Matryoshka to 128) | safetensors; QAT checkpoints; GGUF not named | `embeddinggemma` 622 MB, 2K ([Ollama](https://ollama.com/library/embeddinggemma)) | 0.62 GB. Fits |

Quality and languages (model cards / primary sources only; scores are NOT comparable across rows, because each lab quotes a different MTEB version):
- BGE-M3: "more than 100 working languages" ([card](https://huggingface.co/BAAI/bge-m3), [paper](https://arxiv.org/abs/2402.03216)). The card does not name Hindi or Telugu, but the paper evaluates on MIRACL, which includes **both Hindi and Telugu** ([MIRACL](https://project-miracl.github.io/)). I did not find numeric MIRACL scores in the text (they are images on the card).
- Harrier 0.6B: MTEB v2 multilingual 69.0 (270M: 66.5; 27B: 74.3). Language tag "94 languages"; **Hindi is listed, Telugu is not** (so Telugu is unconfirmed). Queries must carry a one-line instruction prefix ("Instruct: ... Query: ..."), or quality drops ([card](https://huggingface.co/microsoft/harrier-oss-v1-0.6b)).
- Granite R2 311M: MTEB multilingual retrieval (18 tasks) 65.2; enhanced support for 52 languages **including Hindi and Telugu** ([card](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)). Best explicit Hindi + Telugu statement of all candidates.
- Qwen3-Embedding-0.6B: MTEB multilingual mean (task) 64.33, English v2 70.70; "100+ languages", Hindi/Telugu not named ([card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)).
- EmbeddingGemma 1: MTEB multilingual v2 61.15, English v2 69.67; "100+ languages", Hindi/Telugu not named ([card](https://huggingface.co/google/embeddinggemma-300m)). EmbeddingGemma 2: multilingual v2 61.36, English v2 68.46, code 78.68; "100+ languages", Hindi/Telugu not named ([card](https://huggingface.co/google/embeddinggemma-2)). So v2 is a multimodal and code upgrade, not a text-retrieval jump.
- F2LLM-v2 (codefuse-ai, Apache 2.0, March 2026, sizes 80M to 14B) claims top Indic results in its paper, but I found no Hindi/Telugu numbers and the card has no MTEB table, so I left it out of the table ([card](https://huggingface.co/codefuse-ai/F2LLM-v2-0.6B)).
- I could not read the live MTEB leaderboard (it loads dynamically), so no leaderboard rank is quoted. See the test plan: build your own Hindi/Telugu/English retrieval check.

Trade-offs:
- **Keep BGE-M3 as the safe default**: MIT, 8K context, proven, one model also gives sparse and multi-vector output (card), already in your plan. Its weakness is age (Feb 2024).
- **Try Granite R2 311M and Harrier 0.6B as challengers.** Both are newer, both state higher scores on their own cards, both are permissive (Apache 2.0 / MIT), and Granite explicitly names Hindi and Telugu. They are not directly comparable to BGE-M3's scores, so the decision must come from your own test.
- **Re-embedding cost:** whatever you pick, pgvector stores a fixed dimension (1024 for BGE-M3 / Harrier 0.6B, 768 for Granite). Switching later means re-embedding everything. Decide before filling the database.
- EmbeddingGemma 1 has a Gemma-terms licence and only 2K context; skip it. EmbeddingGemma 2 fixes both (Apache 2.0, 8K) but its card shows no better multilingual text score, and it names no Hindi/Telugu, so it is not a reason to switch.

---

## Role 5. Reranker

A reranker re-orders the top 20-100 search hits. It runs after the embedding search, so it only needs to be fast on a few dozen short passages. Ollama has no reranker endpoint that I verified; run these with sentence-transformers (already in the stack) or llama.cpp.

| Candidate | HF repo | Params | Released | Licence | Context | Formats / GGUF | Ollama | 4-bit / memory |
|---|---|---|---|---|---|---|---|---|
| **bge-reranker-v2-m3** (current pick) | [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | 0.6B (XLM-RoBERTa, built on bge-m3) | HF listing: updated 2024-06-24 ([search](https://huggingface.co/models?search=reranker&sort=trending)); card gives no release date | Apache 2.0 | no limit stated; examples use 512 | safetensors; no GGUF on card (community only) | not available (not verified) | about 1.2 GB in FP16 (estimate). Fits GPU and Mac |
| **Qwen3-Reranker-0.6B** | [Qwen/Qwen3-Reranker-0.6B](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B) | 0.6B (LLM-style, yes/no scoring) | paper 2025-06-05; HF listing update "Apr 16" (year not shown) | Apache 2.0 | 32K | safetensors; GGUF only third-party, e.g. [ggml-org Q8_0](https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF) ([search](https://huggingface.co/models?search=Qwen3-Reranker-0.6B-GGUF&sort=downloads)) | not available (not verified) | about 0.65 GB at Q8_0 (estimate). Fits |
| **Qwen3-Reranker-4B** | [Qwen/Qwen3-Reranker-4B](https://huggingface.co/Qwen/Qwen3-Reranker-4B) (card not read) | 4B | same release as above | Apache 2.0 (card not read; assumed same family, unverified) | 32K (unverified) | not checked | not checked | about 2.4 GB at 4-bit (rule of thumb). Fits, but slower |
| **jina-reranker-v3** | [jinaai/jina-reranker-v3](https://huggingface.co/jinaai/jina-reranker-v3) | 0.6B | paper 2025-09-29 | **CC BY-NC 4.0** (non-commercial; commercial needs Jina's permission) | up to 131K, 64 docs per call | safetensors | not checked | fits |

Quality notes (model cards only):
- Qwen3-Reranker-0.6B: MTEB-R 65.80, CMTEB-R 71.31, MMTEB-R 66.36, MLDR 67.28, all measured re-ranking the top 100 hits of Qwen3-Embedding-0.6B ([card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)). "100+ languages"; Hindi/Telugu not named.
- bge-reranker-v2-m3: described as "strong multilingual capabilities"; benchmark results are charts only (BEIR, MIRACL, CMTEB, llama-index), no numbers in text ([card](https://huggingface.co/BAAI/bge-reranker-v2-m3)). MIRACL includes Hindi and Telugu, so the charts do cover them, but I could not read the values.
- jina-reranker-v3: BEIR 61.94, MIRACL 66.83 ([card](https://huggingface.co/jinaai/jina-reranker-v3)); non-commercial licence.
- I searched for 2026 rerankers from Microsoft (Harrier), IBM and mxbai on Hugging Face and found no repos for those ([search](https://huggingface.co/models?search=harrier-oss-reranker+OR+granite-reranker+OR+mxbai-rerank&sort=downloads)), so no newer permissive reranker was verified. (The search may be incomplete.)

Trade-offs:
- **Keep bge-reranker-v2-m3** if you use BGE-M3: same base, same tokenizer, and the combination is the one the BGE project documents. It is MIT/Apache-class clean.
- **Qwen3-Reranker-0.6B is the realistic challenger**: 32K context (good for long chunks), Apache 2.0, and it publishes numbers. Its scores were measured on Qwen embeddings' candidates, so re-test on your own candidates.
- Reranking cost is small: score 30 chunks of about 300 tokens once per question. It is not a bottleneck on either machine.
- Avoid jina-reranker-v3 for anything you might publish: CC BY-NC 4.0.

---

## Role 6. Speech-to-text (verbatim English, word timestamps, keeps fillers, Indian accents; Hindi/Telugu bonus)

Key requirement: **fillers (um, uh) must stay in the text.** No model card I read promises this for Whisper. OpenAI's speech-to-text guide lists "preserving punctuation, capitalization, and filler words" as something a *prompt* can do ([OpenAI docs](https://developers.openai.com/api/docs/guides/speech-to-text)), which suggests Whisper drops fillers by default and an `initial_prompt` containing fillers is the workaround. That is for OpenAI's hosted API; the same trick on local Whisper must be tested (see test plan).

| Candidate | HF repo | Params | Released | Licence | Languages (English / Hindi / Telugu) | Word timestamps | Formats / who publishes | Memory and fit |
|---|---|---|---|---|---|---|---|---|
| **Whisper large-v3-turbo** (current pick) | [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) | 809M (decoder cut from 32 to 4 layers) | HF card: no date (large-v3 family, 2023-24) | MIT | 99 languages; Hindi `hi` and Telugu `te` are in Whisper's language table ([tokenizer.py](https://raw.githubusercontent.com/openai/whisper/main/whisper/tokenizer.py)), but the card warns accuracy is lower on low-resource languages and strong in "~10 languages" | Yes (`return_timestamps="word"`; faster-whisper `word_timestamps=True`) | safetensors (OpenAI). faster-whisper uses CTranslate2 conversions (Systran publishes [large-v3](https://huggingface.co/Systran/faster-whisper-large-v3); the README uses the alias `"turbo"`; the exact turbo repo was not confirmed) ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)). Mac: [mlx-community/whisper-large-v3-turbo](https://huggingface.co/mlx-community/whisper-large-v3-turbo), 1.61 GB | OpenAI README: about 6 GB VRAM, about 8x faster than large ([README](https://github.com/openai/whisper)). faster-whisper int8 uses roughly half the memory of fp16 (large-v2: 2.9 GB int8 vs 4.5 GB fp16 on an RTX 3070 Ti 8 GB). So **fits the 3060 alone**, but not next to a 6 GB chat model. Mac: fits |
| **Whisper large-v3** (accuracy reference) | [openai/whisper-large-v3](https://huggingface.co/openai/whisper-large-v3) (card not read) | 1550M (README table) | 2023 (unverified, card not read) | MIT | same table | Yes | CT2 by [Systran](https://huggingface.co/Systran/faster-whisper-large-v3), fp16 weights | README: about 10 GB VRAM in PyTorch fp16; faster-whisper int8 should fit 6 GB (large-v2 int8: 2.9 GB) but a long transcribe can spike with batching (batch 8 int8: 4.5 GB). Slower than turbo |
| **Parakeet-TDT-0.6B-v3** | [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | 600M | 2025-08-14 | CC-BY-4.0 (commercial OK, attribution needed) | 25 **European** languages with auto-detection; no Hindi, no Telugu | Yes (word, segment, char) | NeMo checkpoint (.nemo); input 16 kHz mono wav/flac; community ONNX/MLX ports exist (not checked) | card: "at least 2GB RAM to load". **Fits easily**. Filler handling not stated; accented-speech WER not reported |
| **Voxtral Mini 3B (2507)** | [mistralai/Voxtral-Mini-3B-2507](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507) | about 3B (5B in metadata) | July 2025 (paper 2025-07-17) | Apache 2.0 | 8 languages incl. English and **Hindi**; no Telugu | not mentioned | safetensors; GGUF not named | card: about 9.5 GB GPU RAM in bf16. **Does not fit 6 GB** without 4-bit |
| **IndicConformer 600M multilingual** (AI4Bharat) | [ai4bharat/indic-conformer-600m-multilingual](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) | 600M | not stated (updated ~1 month before 2026-11-07) | MIT | 22 Indian languages incl. **Hindi and Telugu**; English not listed | not mentioned | ONNX; needs `trust_remote_code=True` (conflicts with your "trust_remote_code off" rule) and gated access | small; **fits**. Hindi WER 13.2 on the Vaani benchmark. The card points to a newer AI4Bharat "Indic-Transcribe" model (25 languages); its page returned 401, so it is not verified |
| **Canary-Qwen-2.5B** | [nvidia/canary-qwen-2.5b](https://huggingface.co/nvidia/canary-qwen-2.5b) | 2.5B | 2025-07-17 | CC-BY-4.0 | English only | not mentioned | .nemo / safetensors BF16 | no memory figure on card; about 5 GB in BF16 by 2 bytes/param (estimate): **too big next to anything else** |

Quality notes (model cards and primary papers only):
- Whisper large-v3-turbo: Open ASR leaderboard mean WER 7.83, RTFx 200, AMI 16.13; "minor quality degradation" vs large-v3; may produce text that was not spoken and can loop ([card](https://huggingface.co/openai/whisper-large-v3-turbo)).
- Parakeet v3: LibriSpeech clean 1.93 / other 3.59 ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)). Canary-Qwen-2.5B: Open ASR mean 5.63, AMI 10.18; the card says it was trained to skew toward verbatim output "including conversational speech disfluencies such as repetitions" ([card](https://huggingface.co/nvidia/canary-qwen-2.5b)). That is the only card I read that talks about disfluencies in training, but it is English only and big.
- Voxtral Mini 3B: Open ASR mean 7.05, Hindi WER 21.3 on Vaani ([card](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507)).
- **Indian-accented English:** the AI4Bharat Svarah benchmark (9.6 h, 117 speakers, 19 accent groups) reports Whisper large WER 7.2, Whisper medium 8.3, Whisper base 13.6, Azure IN 21.3, Google IN 20.7 ([Svarah](https://github.com/AI4Bharat/Svarah)). Those are older Whisper versions, not v3-turbo, so it is only an indication. I found no primary Svarah number for turbo, Parakeet or Granite.
- Granite Speech 5.0 2B (IBM, released 2026-10-20, Apache 2.0): English, French, German, Spanish, Portuguese, Japanese only; no Hindi/Telugu; word timestamps and fillers not described on the card; ships GGUF (`ibm-granite/granite-speech-5.0-2b-GGUF`, IBM recommends Q8_0) and an Ollama build `ibm/granite5-speech` 3.2 GB ([card](https://huggingface.co/ibm-granite/granite-speech-5.0-2b)). Interesting and new, but it fails the Hindi/Telugu bonus and has no stated timestamps.
- Moonshine (Useful Sensors; MIT): speech-to-text list is English, Spanish, German, Mandarin, Japanese, Korean, Vietnamese, Tagalog, Ukrainian, Arabic. No Hindi or Telugu for speech-to-text; word timestamps not mentioned ([GitHub](https://github.com/moonshine-ai/moonshine)).
- Gemma 4 E4B accepts audio input too (CoVoST 35.54, FLEURS 0.08 on its card), but it is a chat model, not a transcriber with word timestamps. Not recommended for this job.
- Sarvam (sarvamai on HF) lists text models and translation only; no open speech model found there ([org page](https://huggingface.co/sarvamai)).
- Newest from NVIDIA: Nemotron 3.5 Transcribe is a 30B-A4B (about 34B total) model ([HF search](https://huggingface.co/models?search=nemotron+transcribe&sort=trending); the official card returned 401 to me, so languages, licence and filler handling are not verified). Its smallest official file is an NVFP4 of about 19B, so it **does not fit** this hardware.

Trade-offs:
- **Confirm Whisper large-v3-turbo** (faster-whisper on the server, mlx-whisper on the Mac). It is the only candidate that has word timestamps, Hindi and Telugu in its language table, MIT licence, and an Apple build. The weak points are filler removal and hallucinations on silence; both need testing and a VAD in front (you already have Silero VAD in the stack).
- **Fillers are the open risk.** If turbo drops "um/uh" even with a prompt, the fallback is to use Whisper large-v3 (not distilled) for the scored practice sessions only, or to detect filled pauses with code (pause and energy features) instead of from the text.
- **Parakeet v3 is the speed alternative for English-only live mode** (small, word timestamps, 2 GB RAM), but its filler handling and Indian-accent accuracy are unreported, and it has no Hindi/Telugu.
- **For Hindi/Telugu notes** (not coaching), IndicConformer is the specialised option; treat it as a separate, optional tool, because of `trust_remote_code` and no English.
- GPU sharing: for live voice, the stack's idea of a smaller Whisper next to Gemma is right, because turbo in int8 (estimate: about 2-3 GB; not stated by a source) plus a 6 GB chat model will not fit 6 GB VRAM together.

---

## Role 7. Text-to-speech (natural English, fast on GPU/CPU, permissive licence, Indian-English voice a bonus)

| Candidate | HF repo / source | Params | Released | Licence | Languages and voices | Formats | Memory and speed | Fit |
|---|---|---|---|---|---|---|---|---|
| **Kokoro-82M** (current pick) | [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | 82M | v1.0 2025-01-27 | Apache 2.0 | v1.0: 8 languages, 54 voices. American English 20 voices (best grade A for `af_heart`, A- `af_bella`), British English 8, **Hindi 4 voices (grade C)**, no Indian-English voice, no Telugu ([VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)) | PyTorch; ONNX through [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (MIT code): about 300 MB, about 80 MB quantized | kokoro-onnx: "near real-time on macOS M1"; no GPU/CPU real-time-factor numbers given. Model card: not stated | **Fits anywhere**, runs on CPU. Mac and server |
| **Indic Parler-TTS** (AI4Bharat) | [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) | 0.9B (F32) | not stated (collection updated Dec 2024) | Apache 2.0 | 21 languages incl. English (Indian English), Hindi, Telugu; 69 named voices (21 English; Hindi: Rohit, Divya; Telugu: Prakash, Lalitha) | safetensors F32 | memory not stated (about 3.6 GB weights in F32, my estimate); speed not stated | Fits the 3060 alone; **too heavy to share the GPU** with a 6 GB chat model; slower than Kokoro |
| **Chatterbox** | [ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox) | 500M (Llama backbone) | not stated | MIT | original: English only; Multilingual V3 covers 23+ languages including Hindi (no Telugu named); voice cloning from a reference clip, so an Indian-English voice is possible if you supply a clip of a speaker who agreed. Built-in PerTh watermark in every file | PyTorch; WAV out | VRAM not stated; speed not stated (the "sub-200 ms" claim is for Resemble's paid service) | probably fits 6 GB alone (500M); not verified |
| **Piper** | [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl) | per-voice, not stated | not stated | **GPL-3.0** (copyleft) | list includes `hi_IN` and `te_IN`; no `en_IN`; voice names not read | ONNX | not stated on the page | tiny, CPU-friendly (general knowledge, not verified from the page) |
| **Kyutai TTS 1.6B (en/fr)** | [kyutai/tts-1.6b-en_fr](https://huggingface.co/kyutai/tts-1.6b-en_fr) | 1.8B (card says "not 1.6B") | paper 2025-09-10 | CC-BY 4.0 weights | English and French only | PyTorch / Moshi stack | GPU memory not stated; streaming, about 75x real time on a big GPU (card) | **too big** to share 6 GB; no Indian voices |
| **Qwen3-TTS-12Hz-0.6B** | [Qwen/Qwen3-TTS-12Hz-0.6B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base) | 0.9B listed (name says 0.6B) | tech report 2026-01-22 | Apache 2.0 | 10 languages (zh, en, ja, ko, de, fr, ru, pt, es, it); no Hindi; 3-second voice cloning; latency "as low as 97 ms" | BF16 safetensors | memory not stated | probably fits alone; not verified |
| **Phonon 31M (Gradium)** | [Ollama phonon](https://ollama.com/library/phonon) | 31M | about 2026-10 (listed "1w") | Apache 2.0 for the 31M English model; the 40M models are **CC BY-NC 4.0** | English (31M); multilingual 40M covers fr/de/es/pt/en | Ollama, **Apple Silicon only**, needs Ollama 0.40.9+ | about 121 MB loaded on an M5 Max | Mac backup only; no Indian voice |
| **IndicF5** (Hindi/Telugu only) | [ai4bharat/IndicF5](https://huggingface.co/ai4bharat/IndicF5) | 0.4B | not stated (2025 citation) | MIT | 11 Indian languages incl. Hindi, Telugu; **English not listed**; needs a reference clip plus its transcript; card says the newer "Indic-Speak" (22 languages) is recommended | PyTorch | not stated | fits; not an English coach voice |
| **OmniVoice** | [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice) | 0.6B | about April 2026 (arXiv 2604.00688) | code Apache 2.0, **weights CC-BY-NC** | 600+ languages claimed; Hindi/Telugu not named | PyTorch | RTF 0.025 claimed | non-commercial licence: avoid |

Trade-offs:
- **Keep Kokoro** for English feedback and shadowing sentences: smallest, Apache 2.0, runs on CPU so it never competes with the LLM for VRAM. Use `af_heart` or `af_bella` (the two highest-graded voices). Hindi voices exist but are graded C.
- **There is no Indian-English voice in Kokoro.** The two honest options: Indic Parler-TTS (real Indian English, Apache 2.0, but 0.9B and heavier) or Chatterbox with a consented reference clip. For a pronunciation coach, a General American or British model voice is usually the target anyway, so this is a bonus, not a need.
- Kokoro's own card says it was trained on a few hundred hours of permissive data and warns that look-alike "kokoro" websites are not affiliated with it. Download only from the `hexgrad` repo.
- Avoid GPL (Piper) if you might publish the code with a different licence, and avoid CC-BY-NC models (Phonon 40M, OmniVoice) for anything beyond private use.

---

## Role 8. Phoneme recognition (IPA/phonemes for pronunciation scoring, used with forced alignment)

This role is the thinnest in the open ecosystem: most phoneme models are small research checkpoints with no stated error rates on the card. Treat any score you get as a rough signal (the stack file already calls pronunciation "rougher than Azure").

| Candidate | HF repo | Params | Released | Licence | Languages | Output | Formats | Fit |
|---|---|---|---|---|---|---|---|---|
| **wav2vec2-lv-60-espeak-cv-ft** (current pick) | [facebook/wav2vec2-lv-60-espeak-cv-ft](https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft) | not stated (wav2vec2-large-lv60 base) | paper 2021-09-23 | Apache 2.0 | "multilingual" (not listed); fine-tuned on Common Voice | eSpeak-style IPA phoneme string (example "m ɪ s t ɚ k w ɪ l t ɚ"); needs a phoneme dictionary to map to words; PER not reported | Transformers / PyTorch; 16 kHz input | large wav2vec2 model: roughly 1.2 GB in fp32 (my estimate, not on the card). **Fits** easily on GPU or Mac |
| **wav2vec2-xlsr-53-espeak-cv-ft** | [facebook/wav2vec2-xlsr-53-espeak-cv-ft](https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft) | not stated (XLSR-53 large) | same 2021 paper | Apache 2.0 | "multiple languages" (not listed; Hindi/Telugu not named) | same | same | similar size. **Fits** |
| **POWSM (CTC)** | [espnet/powsm_ctc](https://huggingface.co/espnet/powsm_ctc) | not stated | paper (PRiSM) 2026-01-20 | CC-BY-4.0 | multilingual, trained on IPAPack++; no language list on the card | IPA phones; the encoder-decoder [espnet/powsm](https://huggingface.co/espnet/powsm) supports CTC forced alignment through `force_align.py` | ESPnet; 16 kHz, fixed 20 s windows | not stated; probably fits. Needs the ESPnet toolkit (heavier setup) |
| **POWSM (encoder-decoder)** | [espnet/powsm](https://huggingface.co/espnet/powsm) | not stated | paper 2025-10-28; retrained text-norm version Jan 2026 | CC-BY-4.0 | multilingual (IPAPack++) | phone recognition, ASR, G2P and P2G in one model; "outperforms or matches specialized PR models of similar size" (no numbers on card) | ESPnet | not stated |
| **ZIPA (large CR-CTC)** | [anyspeech/zipa-large-crctc-ns-800k](https://huggingface.co/anyspeech/zipa-large-crctc-ns-800k) | not stated | not stated | **CC-BY-NC-SA-4.0** (non-commercial, share-alike) | not stated on the card | IPA tokens (`tokens.txt`) | ONNX fp32 / fp16 / int8 | int8 ONNX is small and CPU-friendly; licence limits it to private/non-commercial use |

Notes:
- Only the two Facebook checkpoints state "eSpeak" labels in their names. The wav2vec2 pair output **phoneme labels without word boundaries or stress**, so you align them with the expected phonemes of the target text (from espeak-ng/phonemizer) using CTC forced alignment, then score each phone. The card does not describe this scoring recipe; it is the usual way to use such a model.
- None of the cards report accuracy on Indian-accented English, Hindi or Telugu. Common Voice (the fine-tuning data) is mostly native or near-native speech, so expect false "errors" on valid Indian-English sound patterns (retroflex /t/ /d/, v/w merging). Test this (see test plan).
- POWSM's Jan 2026 retraining and its explicit forced-alignment script make it the most interesting newer option, but the ESPnet dependency is heavier than plain Transformers.
- I searched Hugging Face for other phoneme recognisers; the results were mostly single-language research models (Japanese, Arabic, Korean, Tamil, etc.), TIMIT-based English models, or L2-ARCTIC fine-tunes, with no stated licence or quality on the list pages. I did not read those cards.

Trade-offs:
- **Keep wav2vec2-lv-60-espeak-cv-ft as the baseline**: Apache 2.0, plain Transformers, fits easily, and it matches the Montreal Forced Aligner/phonemizer toolchain in your stack. Its age (2021) and unreported error rates are the risks.
- **Try POWSM CTC as the challenger** if the baseline is too noisy. Licence CC-BY-4.0 (attribution needed).
- Do not treat the phoneme output as a grade. Use it as one signal next to Whisper's word confidence and the optional Azure score.

---

## Role 9. Small vision and OCR (printed screenshots, PDFs, handwritten notes with maths; fits 6 GB VRAM)

Two different jobs hide in this role: (a) **document parsing** (printed PDFs and screenshots to Markdown/tables/LaTeX, which Docling does) and (b) **reading handwriting and maths**, which needs a VLM. Memory figures marked "estimate" use 2 bytes per parameter for BF16 files; none of these cards states a VRAM need.

| Candidate | HF repo / source | Params | Released | Licence | Languages | Handwriting / maths | Formats | Fit |
|---|---|---|---|---|---|---|---|---|
| **RapidOCR via Docling** (current pick, baseline) | [RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR), [docling-project/docling](https://github.com/docling-project/docling) | OCR models: sizes not stated | not stated (v1.1.0 images referenced) | RapidOCR code Apache 2.0, models Apache 2.0 (per README, see MODEL_LICENSES.md); Docling code MIT (models have separate licences) | "default support for Chinese and English"; Hindi/Telugu not mentioned | handwriting not mentioned; no maths | ONNX Runtime, OpenVINO and others; CPU speed not stated | CPU/ONNX, no VRAM. Fits both machines |
| **Granite-Docling-258M** | [ibm-granite/granite-docling-258M](https://huggingface.co/ibm-granite/granite-docling-258M) | 258M | 2025-09-17 | Apache 2.0 | English primary; Japanese, Arabic, Chinese experimental; no Hindi/Telugu | formulas to LaTeX (equation edit distance 0.073, F1 0.968), code, tables (TEDS 0.96-0.97); handwriting not mentioned | safetensors; separate MLX repo for Apple Silicon; quantised builds for llama.cpp/Ollama listed (format not named) | about 0.5 GB in BF16 (estimate). **Fits easily**. Docling runs it via `--vlm-model granite_docling` |
| **PaddleOCR-VL-1.6** | [PaddlePaddle/PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) | 0.9B (1.0B in metadata) | 2026-05-28 | Apache 2.0 | EN/ZH tagged "multilingual" (v1.6 card names no Hindi/Telugu). The earlier [PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) (2025-10-16) says 109 languages, **Hindi named, Telugu not** | v1 card: handwritten text and handwritten formulas supported; v1.6 card does not mention handwriting; formula recognition supported | safetensors BF16; needs PaddlePaddle 3.2.1+ (extra framework); GGUF only community (9 listed on v1 card) | about 2 GB in BF16 (estimate). **Fits 6 GB** |
| **Qwen3.5-4B** (general VLM) | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | 4B (includes vision encoder) | Feb 2026 | Apache 2.0 | 201 languages claimed | MathVista 85.1, MMMU 77.6, OmniDocBench 1.5 86.2 (Qwen's own scale, higher is better); no handwriting benchmark on the card | Ollama `qwen3.5:4b` takes image input, 3.3-4.0 GB; MLX tags exist | 3.3 GB: **fits**. The same model as the Role 2 checker |
| **Qwen3.5-2B** | [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) | 2B | Feb 2026 | Apache 2.0 | 201 languages | MathVista 76.7 (thinking) / 73.9, OmniDocBench 1.5 79.8 / 80.9, OCRBench 84.5 / 85.4 | Ollama `qwen3.5:2b` 2.7-3.1 GB | **Fits** with lots of room |
| **Gemma 4 E4B / E2B** | [google/gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) | 4.5B / 2.3B effective | 2026 | Apache 2.0 | 140+ languages pre-trained | OmniDocBench 1.5 edit distance 0.181 (E4B), 0.290 (E2B) (lower is better); MATH-Vision 59.5 (E4B), 52.4 (E2B); MMMU Pro 52.6 / 44.2 | see Role 1 | E2B fits; E4B borderline (Role 1) |
| **dots.ocr** | [rednote-hilab/dots.ocr](https://huggingface.co/rednote-hilab/dots.ocr) | 1.7B LLM; 3B in metadata | 2025-07-30 | MIT | tagged EN/ZH/multilingual; Hindi/Telugu not named | formulas to LaTeX (OmniDocBench EN formula edit 0.329); handwriting not mentioned | safetensors BF16 | about 6 GB in BF16 (estimate): **does not fit** without 4-bit; no official quant |
| **Nanonets-OCR2-3B** | [nanonets/Nanonets-OCR2-3B](https://huggingface.co/nanonets/Nanonets-OCR2-3B) | 4B in metadata (Qwen2.5-VL-3B base) | collection updated 2025-10-13 | **not stated on the page** | EN, ZH, FR, ES, PT, DE, IT, RU, JA, KO, AR "and many more" | **handwritten documents and LaTeX equations explicitly supported** | safetensors BF16; quantised builds listed (8) | about 8 GB in BF16 (estimate): **does not fit** without 4-bit |
| **olmOCR-2-7B** | [allenai/olmOCR-2-7B-1025](https://huggingface.co/allenai/olmOCR-2-7B-1025) | 8B (Qwen2.5-VL-7B base) | collection updated 2025-12-23; model date not stated | Apache 2.0 | English | math focus (Old Scans Math 82.1); handwriting not mentioned; olmOCR-Bench 82.3 | BF16 and an FP8 build | **too big** (8 GB at FP8) |
| **DeepSeek-OCR** | [deepseek-ai/DeepSeek-OCR](https://huggingface.co/deepseek-ai/DeepSeek-OCR) | 3B | paper 2025-10-21 | MIT | "multilingual", no list | not mentioned; olmOCR-Bench 75.7 | safetensors BF16 | about 6 GB in BF16 (estimate): **tight / no** |

Not read (the task named them, but they cost more context than they would add): GOT-OCR 2.0, Florence-2, TrOCR, SmolVLM, Qwen3-VL small sizes, LFM VL models. Liquid's Ollama page lists `lfm3-vl` (2B, vision + tools, 1 week old on 2026-11-07) and the LFM2.5-VL-3B on HF ([Liquid org](https://huggingface.co/LiquidAI)) but I did not read their cards. IBM's Granite 4.0 3B Vision (2026-03-27, Apache 2.0) is for charts, tables and key-value extraction, English only, no handwriting or maths mentioned ([card](https://huggingface.co/ibm-granite/granite-4.0-3b-vision)).

Trade-offs:
- **Keep RapidOCR + Docling for printed material**: no GPU, MIT/Apache, and the stack already has it. Add **Granite-Docling-258M** as a VLM option for pages with formulas and tables; it is tiny and Apache 2.0.
- **"A small VLM" for handwriting and maths: use the Qwen3.5-4B you already load as checker.** It reads images, has the best published maths-vision numbers among models that fit (MathVista 85.1), and costs no extra disk or VRAM. It is also a general model, so it can explain the maths it read. No card gives a handwriting score, so measure on your own notes.
- **PaddleOCR-VL is the best purpose-built OCR model that fits 6 GB** and its v1 card names Hindi and handwriting, but it needs the PaddlePaddle framework (a second deep-learning stack to maintain). Try it only if Docling + Qwen3.5 fail on your pages.
- **Nanonets-OCR2-3B is the only specialist whose card promises handwriting plus LaTeX**, but the licence is not stated on the page and it needs 4-bit to fit. Check the licence in the repo files before use.
- **Maths safety:** whichever model reads the maths, check the result with SymPy (already in the stack). OCR of handwritten formulas is the weakest spot in the stack file, and no source here promises it is solved.

---

## What changed from the current plan (section 5.4 of the stack file)

| Item in 5.4 / section 2 | Finding | Change |
|---|---|---|
| Gemma 4 E4B "fully in 6 GB, also on the Mac" | Ollama Q4_K_M is 6.6 GB; QAT 6.1 GB; official llama.cpp QAT GGUF 5.15 GB ([Ollama tags](https://ollama.com/library/gemma4/tags), [HF GGUF](https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf)). Google's own table says 4.5 GB for Q4_0 weights ([docs](https://ai.google.dev/gemma/docs/core)). The Mac budget (about 5 GB) is exceeded too | Keep as the target but **test the fit first**; use Gemma 4 E2B (4.3-4.6 GB) on the Mac. Update the "Runs fast" row for the Mac |
| "Small Qwen 3.5" checker | Pick the 4B (not 2B). Thinking is on by default and breaks JSON-only prompts unless turned off | Name it: `Qwen3.5-4B`. Add Granite 4.2 3B and Nemotron 3 Nano 4B as spare voters |
| Gemma 4 12B at night | Confirmed: 7.0-8.0 GB file, 256K context, Apache 2.0. Google also ships a 0.4B drafter for up to 3x faster decoding (support in Ollama unconfirmed) | Keep. Add Qwen3.5-9B as the alternative to blind-test |
| gpt-oss 20B "test first" | 12.1 GB (GGUF) to 14 GB (Ollama) file vs 6 GB VRAM + 6-8 GB free RAM | Remove from the 16 GB plan. After the 32 GB upgrade, test Gemma 4 26B A4B first (3.8B active, 14.4-18 GB), then gpt-oss |
| BGE-M3 | Still valid (MIT, 8K, Hindi/Telugu through MIRACL). Newer options exist: Granite Embedding 311M R2 (2026-04-29; names Hindi and Telugu), Harrier-OSS-v1 0.6B (MTEB v2 multilingual 69.0; Hindi but no Telugu), EmbeddingGemma 2 | Keep BGE-M3; run a Hindi/Telugu retrieval test against Granite R2 and Harrier before filling pgvector |
| "BGE reranker" | bge-reranker-v2-m3 confirmed (Apache 2.0, 0.6B). Qwen3-Reranker-0.6B is the realistic alternative | Name the exact model; add the Qwen option |
| Whisper large-v3-turbo | Word timestamps yes; fillers not guaranteed; Hindi/Telugu supported but weaker. Parakeet v3 has no Hindi/Telugu. Newest Nemotron 3.5 Transcribe is a 30B-A4B, too big | Keep. Add a filler test and an `initial_prompt` trick; keep large-v3 as the accuracy fallback |
| Kokoro | Apache 2.0, 82M, 54 voices; Hindi voices exist (grade C); no Indian-English voice | Keep for English. Add Indic Parler-TTS as an optional Indian-English/Hindi/Telugu voice |
| wav2vec2 phoneme model | Still the simplest; no error rates on the card; Common Voice base so native-speaker bias likely | Keep. Add POWSM CTC (2026) as the challenger |
| "RapidOCR via Docling + a small VLM" (row "small vision model" in section 3) | VLM unnamed in the stack | Name it: Qwen3.5-4B (already loaded as checker). Add Granite-Docling-258M for formulas/tables. PaddleOCR-VL-1.6 as an extra if needed |
| `trust_remote_code` off (section 8.1) | AI4Bharat IndicConformer needs `trust_remote_code=True` | Do not use it, or run it in a sandbox, if you want to keep the security rule |
| "Models only from official sources, in safetensors or GGUF" | Google, IBM, NVIDIA and ggml-org publish official GGUF for some models; Qwen publishes none (only unsloth/lmstudio/bartowski) | Prefer official GGUF where it exists; for Qwen3.5 use unsloth or lmstudio-community and verify hashes |

---

## How to test before trusting

Test on the real machine, with the same Docker settings as production (`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, 8k context). Record memory with `nvidia-smi` (server) and Activity Monitor (Mac).

| Role | Test | Pass line (suggested; adjust to taste) |
|---|---|---|
| 1 Worker | Load `gemma4:e4b-it-q4_K_M`, `gemma4:e4b-it-qat` and the 5.15 GB QAT GGUF in llama.cpp. Check `nvidia-smi`: how many layers on GPU, tokens per second with an 8k prompt. Then 100 labelled news items for tagging, and 50 articles for JSON fact extraction validated by Pydantic | Fully on GPU (or at most a few layers on CPU) with speed you can live with; at least 90% tag agreement; at least 98% valid JSON on the first try. If it fails, drop to E2B or Qwen3.5-4B (thinking off) and repeat |
| 2 Checker | Give it 50 MCQs: 25 with a deliberately wrong key, 25 correct. Run thinking on with a token cap. Also run with thinking off for JSON | Catches at least 90% of the wrong keys; flags at most 5% of the correct ones; no thinking loops |
| 3 Night writer | Same 3 deep-dive prompts on Gemma 4 12B, Qwen3.5-9B (and later Gemma 4 26B A4B). Measure GPU/RAM split, tokens per second, RAM left for the OS. Blind-rate the output | Finishes a 1,500-word piece overnight without swapping; you prefer it over the 4B model in a blind test. Try the drafter only if the Ollama build supports it |
| 4 Embeddings | Build 30 questions each in English, Hindi and Telugu with known answer passages from your own sources; compare recall@5 for BGE-M3, Granite R2 311M, Harrier 0.6B (remember the Harrier query prefix). Also test deduplication on near-duplicate news | Pick the one with the best Hindi+Telugu recall without losing more than 2 points on English |
| 5 Reranker | On the same questions, rerank the top 30 with bge-reranker-v2-m3 and Qwen3-Reranker-0.6B; measure latency for 30 chunks | Improves recall@5 or MRR over embeddings alone; under about 1 s on the 3060 |
| 6 STT | Record 10 clips of yourself (2 minutes each, with deliberate "um/uh", Indian accent, plus 3 clips in Hindi and Telugu). Run turbo with and without an `initial_prompt` containing fillers, and large-v3. Compare filler counts against a hand transcript. Test silence for hallucinations (with Silero VAD on) | At least 90% of fillers kept; word timestamps within about 100 ms on spot checks; no invented text in silence; speed several times faster than real time |
| 7 TTS | Generate 20 coaching sentences with Kokoro `af_heart` and `af_bella`; generate 5 with Indic Parler-TTS (Indian English). Time the generation on CPU and GPU | Kokoro faster than real time on CPU; you rate the voice natural. For Parler: decide if the Indian-English voice is worth the extra GPU load |
| 8 Phonemes | Read 20 prepared sentences, once correctly and once with a deliberate error. Phonemize the text with espeak-ng, align, score. Include Indian-English sound patterns that are valid | Catches most deliberate errors; does not flag your normal accent on more than about 10% of phones; compare against POWSM CTC |
| 9 OCR/VLM | 20 printed screenshots/PDF pages (Docling + RapidOCR), 20 handwritten pages with maths (Qwen3.5-4B, then PaddleOCR-VL-1.6 if needed). Verify the maths with SymPy | At least 95% character accuracy on print; handwritten maths flagged "unverified" unless SymPy agrees; accept that handwritten formulas stay weak |

---

## Sources

All URLs in this file. Primary: Hugging Face cards and listings, Ollama library, vendor docs, GitHub. Secondary ones are marked "unverified" in the text (the aimlapi and pulse.bot news pages). Links marked "card not read" in the tables (Ministral-3-14B, Qwen3-Reranker-4B, granite-4.2-8b, whisper-large-v3) were not opened. Hugging Face search/listing pages were fetched through a summarising tool, so counts and download numbers on them may be approximate; the MTEB and Open ASR leaderboards loaded no data, so no leaderboard ranks are quoted.


- https://huggingface.co/google/gemma-4-E4B-it
- https://aimlapi.com/blog/gemma-4---google-deepminds-most-powerful-open-weight-ai-model-family
- https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf
- https://huggingface.co/models?search=gemma-4-E4B-it-GGUF&sort=downloads
- https://ollama.com/library/gemma4/tags
- https://ai.google.dev/gemma/docs/core
- https://huggingface.co/google/gemma-4-E2B-it
- https://huggingface.co/Qwen/Qwen3.5-4B
- https://huggingface.co/models?search=Qwen3.5-4B-GGUF&sort=downloads
- https://ollama.com/library/qwen3.5
- https://huggingface.co/ibm-granite/granite-4.2-3b
- https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF
- https://ollama.com/library/granite4.2
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF
- https://huggingface.co/ibm-granite/granite-4.2-8b
- https://huggingface.co/ibm-granite
- https://huggingface.co/Qwen/Qwen3.5-2B
- https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512
- https://huggingface.co/google/gemma-4-12B-it
- https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf
- https://huggingface.co/models?search=gemma-4-12b-it-GGUF&sort=downloads
- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/mistralai/Ministral-3-14B-Instruct-2512
- https://huggingface.co/mistralai
- https://ollama.com/library/ministral-3
- https://huggingface.co/openai/gpt-oss-20b
- https://huggingface.co/ggml-org/gpt-oss-20b-GGUF
- https://ollama.com/library/gpt-oss
- https://huggingface.co/google/gemma-4-26B-A4B-it
- https://huggingface.co/LiquidAI/LFM2.5-24B-A2B
- https://huggingface.co/google/gemma-4-12B-it-assistant
- https://huggingface.co/BAAI/bge-m3
- https://ollama.com/library/bge-m3
- https://huggingface.co/microsoft/harrier-oss-v1-0.6b
- https://www.pulse.bot/ai/news/microsoft-ai-releases-harrier-oss-v1-a-new-family-of-multilingual-embedding-models-hitting-sota-on-m-4fe260f0-a338-4356-9ce9-984f7c4c1c9b/
- https://huggingface.co/microsoft/harrier-oss-v1-270m
- https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2
- https://huggingface.co/google/embeddinggemma-2
- https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- https://ollama.com/library/qwen3-embedding
- https://huggingface.co/google/embeddinggemma-300m
- https://ollama.com/library/embeddinggemma
- https://arxiv.org/abs/2402.03216
- https://project-miracl.github.io/
- https://huggingface.co/codefuse-ai/F2LLM-v2-0.6B
- https://huggingface.co/BAAI/bge-reranker-v2-m3
- https://huggingface.co/models?search=reranker&sort=trending
- https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF
- https://huggingface.co/models?search=Qwen3-Reranker-0.6B-GGUF&sort=downloads
- https://huggingface.co/Qwen/Qwen3-Reranker-4B
- https://huggingface.co/jinaai/jina-reranker-v3
- https://huggingface.co/models?search=harrier-oss-reranker+OR+granite-reranker+OR+mxbai-rerank&sort=downloads
- https://developers.openai.com/api/docs/guides/speech-to-text
- https://huggingface.co/openai/whisper-large-v3-turbo
- https://raw.githubusercontent.com/openai/whisper/main/whisper/tokenizer.py
- https://huggingface.co/Systran/faster-whisper-large-v3
- https://github.com/SYSTRAN/faster-whisper
- https://huggingface.co/mlx-community/whisper-large-v3-turbo
- https://github.com/openai/whisper
- https://huggingface.co/openai/whisper-large-v3
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3
- https://huggingface.co/mistralai/Voxtral-Mini-3B-2507
- https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
- https://huggingface.co/nvidia/canary-qwen-2.5b
- https://github.com/AI4Bharat/Svarah
- https://huggingface.co/ibm-granite/granite-speech-5.0-2b
- https://github.com/moonshine-ai/moonshine
- https://huggingface.co/sarvamai
- https://huggingface.co/models?search=nemotron+transcribe&sort=trending
- https://huggingface.co/hexgrad/Kokoro-82M
- https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- https://github.com/thewh1teagle/kokoro-onnx
- https://huggingface.co/ai4bharat/indic-parler-tts
- https://huggingface.co/ResembleAI/chatterbox
- https://github.com/OHF-Voice/piper1-gpl
- https://huggingface.co/kyutai/tts-1.6b-en_fr
- https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base
- https://ollama.com/library/phonon
- https://huggingface.co/ai4bharat/IndicF5
- https://huggingface.co/k2-fsa/OmniVoice
- https://huggingface.co/facebook/wav2vec2-lv-60-espeak-cv-ft
- https://huggingface.co/facebook/wav2vec2-xlsr-53-espeak-cv-ft
- https://huggingface.co/espnet/powsm_ctc
- https://huggingface.co/espnet/powsm
- https://huggingface.co/anyspeech/zipa-large-crctc-ns-800k
- https://github.com/RapidAI/RapidOCR
- https://github.com/docling-project/docling
- https://huggingface.co/ibm-granite/granite-docling-258M
- https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6
- https://huggingface.co/PaddlePaddle/PaddleOCR-VL
- https://huggingface.co/rednote-hilab/dots.ocr
- https://huggingface.co/nanonets/Nanonets-OCR2-3B
- https://huggingface.co/allenai/olmOCR-2-7B-1025
- https://huggingface.co/deepseek-ai/DeepSeek-OCR
- https://huggingface.co/LiquidAI
- https://huggingface.co/ibm-granite/granite-4.0-3b-vision
