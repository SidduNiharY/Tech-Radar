# TechRadar Brain: Old Plan vs New Local Models

**As of 2026-11-07.** A short summary of what changed after the model research. The full details, tables and sources are in [03_Local_Models_Research.md](03_Local_Models_Research.md). The current stack is in [02_Tech_Stack_and_Security.md](02_Tech_Stack_and_Security.md), section 5.4.

**Hardware:** ASUS TUF A15 on Linux (RTX 3060 Laptop GPU with 6 GB VRAM, 16 GB RAM) as the server, and a MacBook Air M4 (16 GB) as backup.

**Caveat:** none of this has been run on my hardware yet. Sizes for Gemma 4 and gpt-oss were re-checked on the Ollama library pages; the benchmark scores, licences and release dates come from the research agent's reading of the model cards and were not re-checked. Benchmark scores are the model makers' own numbers, taken on different settings, so they are only a hint.

## 1. Old plan vs new picks

| Job | Old plan | New result |
|---|---|---|
| Daily worker | Gemma 4 E4B, fully on the GPU | **Too big in Ollama:** the 4-bit file is 6.6 GB and the QAT build is 6.1 GB. It stays the target only if it passes a fit test (Google's official QAT file for llama.cpp is 5.15 GB). Fallbacks: Gemma 4 E2B (4.6 GB) or Qwen3.5-4B (about 3.3 GB). The Mac gets E2B |
| Checker | "A small Qwen 3.5" | **Named: Qwen3.5-4B** (not the 2B, which drops sharply when thinking is off). Spare voters: Granite 4.2 3B (2.2 GB) and Nemotron 3 Nano 4B (2.84 GB) |
| Night writer | Gemma 4 12B, with gpt-oss 20B as "test first" | 12B stays (7.2–8.0 GB, split across GPU and RAM). **gpt-oss 20B is dropped** (14 GB file). Qwen3.5-9B is the one to blind-test against it. After a 32 GB RAM upgrade: Gemma 4 26B A4B |
| Embeddings | BGE-M3 | Kept, but to be tested against Granite Embedding 311M R2 and Harrier-OSS-v1 0.6B on Hindi and Telugu |
| Reranker | "BGE reranker" | **Exact model named:** bge-reranker-v2-m3. Alternative: Qwen3-Reranker-0.6B |
| Speech to text | Whisper large-v3-turbo | Kept, but **fillers ("um", "uh") are an open risk** and need a test. Fallback: Whisper large-v3. English-only live mode: Parakeet-TDT-0.6B-v3 |
| Text to speech | Kokoro | Kept. Indic Parler-TTS added as an optional Indian-English, Hindi and Telugu voice |
| Pronunciation | wav2vec2 phoneme model | Kept. POWSM CTC added as a challenger |
| Images and handwriting | "A small vision model" | **Named:** Qwen3.5-4B (already loaded as the checker). Extras: Granite-Docling-258M, PaddleOCR-VL-1.6 |

## 2. Old vs new, in one view

### Old plan (before the research)

- Worker: Gemma 4 E4B
- Checker: small Qwen 3.5
- Night writer: Gemma 4 12B; gpt-oss 20B to test
- Embeddings: BGE-M3
- Reranker: BGE reranker
- Speech to text: Whisper large-v3-turbo
- Text to speech: Kokoro
- Pronunciation: wav2vec2 phoneme model
- Images: RapidOCR + a small vision model

### New plan (after the research)

- Worker: Gemma 4 E4B **if it fits**, else Gemma 4 E2B or Qwen3.5-4B
- Checker: Qwen3.5-4B (spares: Granite 4.2 3B, Nemotron 3 Nano 4B)
- Night writer: Gemma 4 12B (test Qwen3.5-9B too); Gemma 4 26B A4B after a RAM upgrade
- Embeddings: BGE-M3, tested against Granite R2 and Harrier
- Reranker: bge-reranker-v2-m3
- Speech to text: Whisper large-v3-turbo, with a filler test
- Text to speech: Kokoro (+ Indic Parler-TTS optional)
- Pronunciation: wav2vec2 phoneme model (+ POWSM CTC)
- Images: RapidOCR via Docling, Qwen3.5-4B for handwriting and maths

## 3. How newer small models differ from older ones

These points come from the model cards in the research:

| What | Newer small models | Why it matters here |
|---|---|---|
| **Context window** | 128K (Gemma 4, Granite) to 262K (Qwen3.5, Nemotron). Older small models mostly had 4K–32K | Long articles fit. In practice I still run 8k to save memory |
| **Efficient designs** | Qwen3.5 uses a Gated DeltaNet hybrid. Nemotron 3 Nano is a Mamba hybrid with only 4 attention layers. Gemma 4's "E" models store about 8B parameters but use 4.5B at a time | Less memory for the same quality, but the stored size still decides what fits |
| **4-bit builds trained for it (QAT)** | Google's QAT builds are trained to work at 4-bit | Quality should drop less than with a normal compressed copy |
| **Thinking modes** | Qwen3.5 reasons before answering by default | Good for checking MCQs, but it can break JSON-only jobs, so switch it off for those |
| **Tool use and structured output** | Gemma 4, Ministral 3 and Nemotron list function calling on their cards | Better for tagging and fact extraction into JSON |
| **More than text** | Gemma 4 takes images and audio; Qwen3.5 handles images | One model can cover more jobs |
| **Scores for their size** | Qwen3.5-4B reports IFEval 89.8 and MMLU-Pro 79.1; Gemma 4 12B reports MMLU-Pro 77.2 | Strong on paper. Only my own tests count |

## 4. What newer does not fix

- **Size is still the limit.** Gemma 4 E4B is newer but still doesn't fit the GPU in Ollama, and gpt-oss 20B doesn't fit the RAM.
- **Hindi and Telugu support is thin** for speech, voices and search. Granite Embedding R2 is the only embedding card that names both.
- **Licences vary.** Most picks are Apache 2.0 or MIT. Exceptions: jina-reranker-v3 and ZIPA are non-commercial, Piper is GPL-3.0, and Nemotron uses NVIDIA's own licence.
- **`trust_remote_code`:** AI4Bharat's IndicConformer needs it, which breaks the security rule in the stack file, so it stays out.
- **No old-vs-new measurements yet.** The research did not test old models side by side, so there are no measured gains over older generations.

## 5. Still unverified

- Gemma 4's release date (2026-04-02) comes from a secondary source.
- The MTEB and Open ASR leaderboards loaded no data, so no rankings are quoted.
- Several memory figures are arithmetic (0.6 GB per billion parameters), not measurements.
- A few model cards were not opened: Ministral-3-14B, Qwen3-Reranker-4B, granite-4.2-8b and whisper-large-v3.
- Not read: GOT-OCR, Florence-2, TrOCR, SmolVLM, Qwen3-VL, LFM VL and Kyutai STT.
- Whether Ollama supports Google's 0.4B drafter model (claimed up to 3x faster for the 12B) is unconfirmed.

## 6. Next step: test before trusting

Run the test plan in [03_Local_Models_Research.md](03_Local_Models_Research.md) on the TUF A15 and the Mac, in this order:
1. **Gemma 4 E4B fit:** `gemma4:e4b-it-q4_K_M`, `gemma4:e4b-it-qat` and the 5.15 GB QAT GGUF in llama.cpp. Check `nvidia-smi` for layers on the GPU and tokens per second.
2. **Whisper and fillers:** record clips with deliberate "um" and "uh", and compare turbo with and without a filler prompt.
3. **Hindi and Telugu search:** 30 questions per language against BGE-M3, Granite R2 and Harrier.
4. **Checker:** 50 MCQs, half with a deliberately wrong key.
5. **Night writer:** a blind test of Gemma 4 12B against Qwen3.5-9B on three deep-dive prompts.
