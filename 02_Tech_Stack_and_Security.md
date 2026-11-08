# TechRadar Brain: Tech Stack and Security

**As of 2026-11-08.** Updated with the improvements agreed in [06_Improvements.md](06_Improvements.md): Jarvis, the Library, feedback and self-improvement, the Intake Gateway, exam sources and intrusion detection. Companion to [01_Idea_and_Daily_Use.md](01_Idea_and_Daily_Use.md). This file lists every technology in the app, what it does, where it runs, and how the devices stay safe. The build architecture in [05_Architecture.md](05_Architecture.md) turns it into services and numbered security controls, and refines two choices here: LiteLLM runs as a library inside the worker (not a proxy), and the database driver is psycopg 3. Version numbers come from [02_AI_Automation_Simple_Stack.md](../02_AI_Automation_Simple_Stack.md) and its full catalog (checked 2026-11-03); items without a number were not version-checked.

**Model research:** the model picks in section 5.4 come from [03_Local_Models_Research.md](03_Local_Models_Research.md) (Hugging Face model cards and official pages, 2026-11-07).

**Hardware:** a MacBook Air M4 (16 GB) and an ASUS TUF A15 (AMD Ryzen, 16 GB RAM, NVIDIA RTX 3060 Laptop GPU with 6 GB) that dual-boots Linux and Windows. The server runs on the **Linux** side.

## 1. Approach

- **Local-only by default.** The internet is used only to *fetch* information. My own laptops do all the *thinking*, so there is no LLM bill.
- **Optional cloud backup, off by default:** Azure pronunciation scores and Claude for a few weak spots, behind a budget cap.
- **Linux is the server OS.** Docker and the NVIDIA GPU work natively on Linux, with no Windows or WSL2 overhead, and it's what real servers run.
- **Same core as LifeLedger:** Python 3.14, uv, FastAPI, Pydantic v2, PostgreSQL 18, a Telegram bot and Docker Compose, so I learn them once.
- **Different agent framework:** LangGraph here; LifeLedger uses Pydantic AI + Temporal. Together the two projects show both.
- **Shared infrastructure with LifeLedger:** one server, one Postgres server, one Ollama, one Langfuse.
- **A Next.js web app for the main UI:** professional answers, dashboards, quizzes and a live voice screen with a sound-reactive orb. Telegram stays for push messages, Obsidian for notes.
- **Jarvis is the main way I use the app:** one voice assistant for everything (section 5.15). The web app, Telegram and Obsidian stay for reading, charts and alerts.
- **One checked door for data:** every input passes the Intake Gateway before anything else touches it (section 5.16).
- **Prevent, then detect and respond:** the design assumes something may get through, so it adds alarms and automatic containment (section 5.17).

## 2. Devices and roles

| Device | Role | Main jobs |
|---|---|---|
| **ASUS TUF A15 on Linux** (AMD Ryzen, 16 GB RAM, RTX 3060 6 GB) | Home AI server, whenever it's booted into Linux | Runs the app, database, scheduled jobs, Telegram bot, web app, Jarvis, the Intake Gateway, security monitoring, and local models on the GPU |
| **MacBook Air M4** (16 GB, 8-core GPU, no fan) | Daily machine | Jarvis ("Hey Jarvis" in the Jarvis tab), studying in the web app and Obsidian, the Library folder for big PDFs and videos, writing code, Claude Code, backup models |
| **Phone** | Remote control | Jarvis (tap the orb), Telegram (briefings, quizzes, voice notes, alerts), the web app (installed on the home screen), Obsidian |
| **Internet** | Sources and messengers | News, data and exam sources, ClamAV signature updates, Telegram's servers, Tailscale's coordination service, GitHub. Azure and Claude only if turned on |

### What each laptop can run

| | MacBook Air M4 | ASUS TUF A15 (Linux) |
|---|---|---|
| Hardware | M4, 16 GB shared memory, 8-core GPU, no fan | AMD Ryzen (8 cores on most RTX 3060 models), 16 GB RAM, RTX 3060 6 GB, fans |
| Strengths | Quiet, efficient, my daily machine | NVIDIA GPU (CUDA), fans for long runs, Docker and the GPU work natively, can stay plugged in |
| Memory for models | About 4–6 GB, shared with everything else | 6 GB on the GPU, plus roughly 6–8 GB of RAM for overflow (Linux leaves more free than Windows) |
| Runs fast | Gemma 4 E2B, embeddings, mlx-whisper, Kokoro, Apple text recognition | Gemma 4 E2B or Qwen3.5-4B, a second small model as checker, faster-whisper, BGE-M3, Kokoro, pronunciation models |
| Runs slowly (overnight) | — | Gemma 4 12B, split between GPU and RAM |
| Maybe; test first | Gemma 4 E4B: its Ollama file is 6.6 GB, over the Mac's 4–6 GB | Gemma 4 E4B: Ollama file 6.6 GB (QAT 6.1 GB) vs 6 GB of VRAM; the 5.15 GB official QAT GGUF in llama.cpp is the best chance |
| Doesn't fit | 12B and bigger | gpt-oss 20B (12–14 GB file vs about 11–13 GB of VRAM + free RAM), 26B and bigger. After a RAM upgrade, Gemma 4 26B A4B becomes possible |

The two laptops can't be added together into one 32 GB machine. Splitting one model across both (llama.cpp RPC, exo) works in theory but is slow over Wi-Fi, so each laptop gets its own jobs instead.

**Cheap upgrade:** most TUF A15 models have two RAM slots. Going to 32 GB would make Gemma 4 12B comfortable and open up Gemma 4 26B A4B (a mixture-of-experts model with only 3.8B active parameters, so it is fast for its size) and gpt-oss 20B, for far less than a new GPU. Details are in [03_Local_Models_Research.md](03_Local_Models_Research.md).

### How the roles work

```
                  Phone (Telegram, web app, Obsidian)
                            │  Tailscale (private network)
          ┌─────────────────┴──────────────────┐
  TUF A15 (LINUX) = home AI server     MAC = daily machine
  (plugged in, fans, RTX 3060)         (study, coding)
  • Docker: Postgres + pgvector,       • Obsidian vault
    API, scheduler, Telegram bot,      • Claude Code + read-only MCP
    fetchers, Intake Gateway           • Backup Gemma 4 E2B + Whisper
    (sandboxed parser), SearXNG,       • Apple text recognition
    LanguageTool, changedetection.io,  • Code is written here
    Next.js app, Jarvis                • Jarvis tab ("Hey Jarvis")
  • Ollama on the GPU: Qwen3.5-4B      • Library folder for big
    worker, Gemma 4 E2B checker,         PDFs and videos
    Gemma 4 12B at night
  • faster-whisper, BGE-M3, Kokoro,
    pronunciation models
  • Host security: Falco, AIDE,
    auditd, alerter
          └──── vault synced with Syncthing ────┘
```

- **The Linux server** does the heavy, scheduled work: fetching, the news batch, big PDFs and videos overnight, 12B jobs at night, voice analysis, Jarvis, the Telegram bot, the web app and security monitoring.
- **The Mac** is where I study and code, and it keeps Gemma and Whisper as a backup.
- **Model jobs** run on the server's GPU. When the server is off or booted into Windows, jobs wait in the queue and catch up. There's no Mac fallback for server jobs (see 05, decision D19); the Mac's Ollama serves tools on the Mac only.
- **Telegram** keeps undelivered messages for up to 24 hours, so a voice note sent while the server is off is processed when it's back.
- **I develop on the Mac and deploy to the server** with the same Docker Compose file.
- **Dual boot:** the server works only while the laptop is in Linux, so Linux is the default boot entry and Windows is for occasional use.

## 3. Local-only: what works

| Feature | Local-only result | How |
|---|---|---|
| Collect news, remove duplicates, "Rising fast" | ✅ Same as cloud | Code + embeddings |
| Tag, sort, relevance, exam tags | ✅ Good | Gemma 4 E4B (or E2B if E4B doesn't fit) |
| Summaries, the four questions, pulling out facts | ✅ Good when it works only from the article | Gemma 4 E4B (or E2B); 12B at night for harder items |
| Current-affairs MCQs | ✅ Good with the facts-first method | Gemma writes, Qwen checks, 2–3 source rule |
| Foundation pages, glossary | ✅ Good when built from NCERT, Wikipedia and official sources | Gemma + retrieval |
| Weekly deep dive | ⚠️ OK, but shallower than cloud | Gemma 4 12B overnight + sources |
| Explanations for wrong answers, GATE solutions | ⚠️ OK | Official answer keys + 12B + SymPy for maths |
| Forward fact-checker | ⚠️ Finds evidence, weak at final verdicts | SearXNG + Gemma; answers "unverified" when unsure |
| Economy dashboard | ✅ | Official data + code; Gemma writes "what changed" |
| Scorecard screenshots | ✅ | Text recognition + code |
| Handwritten notes | ⚠️ Neat writing is OK, formulas are weak | Text recognition, small vision model |
| Speech to text, word for word | ✅ Same as cloud | faster-whisper (server) / mlx-whisper (Mac) |
| Fillers, speed, pauses, word variety | ✅ | Code |
| Grammar | ✅ | LanguageTool + Gemma explanations |
| Pronunciation | ⚠️ Rougher than Azure | wav2vec2 phoneme model + forced alignment |
| Intonation | ⚠️ Rough | Pitch analysis (Praat via parselmouth) |
| Speech output | ✅ | Kokoro |
| Live conversation | ⚠️ About 1–2 s delay (estimate) | Pipecat + faster-whisper + Gemma + Kokoro on the server's GPU |
| Planner, revision, time tracker, check-in, mock analysis, speed drills | ✅ | Code + Postgres |
| Jarvis (one voice assistant for everything) | ⚠️ About 1–2 s for simple replies (estimate); hard questions take the slow path | openWakeWord on the device, Pipecat, faster-whisper, Qwen3.5-4B router and replies, Kokoro |
| Big PDFs and videos (whole books, long lectures) | ✅ Overnight, resumable | Docling in 25-page parts, ffmpeg in the sandbox, Whisper with timestamps, slide OCR |
| Checking every input (Intake Gateway) | ✅ | File-type checks, pdfid, oletools, ClamAV, YARA, rebuild, a small injection classifier on the CPU |
| Learning my preferences | ✅ | Code (counting, weights), the night model for the weekly pattern review, rules I approve |
| Intrusion detection | ✅ | Falco, AIDE, auditd, pgaudit, Lynis, honeytokens |

**Weak spots:** depth in deep dives and hard explanations, fact-check verdicts, handwritten formulas, pronunciation precision, and a short delay in live voice. The optional cloud backup covers exactly these.

## 4. Making small models good enough

1. **Internet for knowledge, local model for reading.** Small models forget facts but read well. They get the article plus background from Wikipedia, NCERT books and official sources, and answer *only* from that text.
2. **Facts first.** MCQ answers come from facts confirmed by 2–3 independent sources; the model only writes the wording.
3. **Two model families.** Gemma writes and Qwen3.5-4B checks (with thinking on and a token cap for checking; off for JSON-only jobs). Different families rarely make the same mistake. If the worker ever becomes Qwen, the checker switches to Gemma 4 E2B or Granite 4.2 3B.
4. **Big model at night.** Gemma 4 12B is slow but better: it writes deep dives, explanations and foundation pages while I sleep.
5. **Filter before thinking.** Rules and duplicate removal first, then the embedding relevance filter, so only what matters reaches the models.
6. **Code for anything countable.** Trends, flashcard scheduling, maths checks, fillers, speaking speed, word variety, mock analysis.
7. **Test before trusting.** A job goes live only after passing its test set, for example at least 90% agreement with my labels for tagging, and zero wrong answers in 50 sample MCQs.
8. **"Unverified" and ask me** whenever the system isn't sure.

## 5. Technologies by layer

### 5.1 Development

| Tool | Purpose in the app | Runs on |
|---|---|---|
| Python 3.14 | Main language | Mac (development), server (in Docker) |
| uv 0.13 | Installs packages and locks exact versions | Mac, Docker builds |
| Ruff 0.17 | Checks and formats code | Mac, CI |
| pytest 9 | Tests | Mac, CI |
| Git + GitHub (private repo) | Code history; code only, never personal data | Mac, GitHub |
| GitHub Actions | Runs tests, linting and security scans on every push | GitHub (cloud) |
| Docker + Docker Compose | Packages every service; the same file runs on the Mac (development) and the server | Mac (Docker Desktop), server (Docker Engine, no VM) |
| Node.js (LTS) + pnpm 11 | Runs and builds the web app; pnpm installs JavaScript packages with safety settings | Mac (development), server (in Docker) |
| TypeScript + ESLint | Type-safe frontend code and code checks | Mac, CI |
| Claude Code | Coding assistant | Mac |

### 5.2 Backend and data

| Tool | Purpose | Runs on |
|---|---|---|
| FastAPI 0.162 + Uvicorn | Internal API behind the web app: streamed answers, quizzes, dashboard data, health checks | Server (Docker) |
| Pydantic v2 + pydantic-settings | Checks every model answer and every setting | Server (Docker) |
| PostgreSQL 18 | Quizzes, flashcards, scores, news items, check-ins, job queue, LangGraph checkpoints | Server (Docker) |
| pgvector | Search by meaning | Server (inside Postgres) |
| SQLAlchemy 2 + asyncpg + Alembic | Database access and schema changes | Server (Docker) |
| APScheduler | Daily and weekly jobs; catches up after sleep | Server (Docker) |
| Procrastinate | Job queue in Postgres; holds jobs until a machine is free or awake | Server (Docker) |
| Markdown vault | My notes, the source of truth | Written on the server, synced to the Mac |

### 5.3 AI workflows and model serving

| Tool | Purpose | Runs on |
|---|---|---|
| LangGraph 1.2 | Workflows: reader → check → writer, MCQ write → verify, voice analysis | Server (Docker) |
| LangChain 1.4 | Building blocks for models and tools, structured output | Server (Docker) |
| LiteLLM 1.106 (library) | One entry point for all models, inside the worker: server GPU, and the cloud only if enabled | Server (inside the worker) |
| Ollama 0.40 | Runs local models | Server (Docker with the GPU); Mac (native, backup) |
| NVIDIA Container Toolkit | Lets Docker containers use the RTX 3060 | Server |
| nvidia-ml-py (NVML) | Reads GPU memory, temperature and load for the Models screen | Server |
| faster-whisper | Speech to text on the NVIDIA GPU | Server |
| mlx-whisper | Speech to text on the Mac (backup) | Mac |
| Pipecat 1.15 | Live voice conversation pipeline (Voice Coach v2, then Jarvis's audio) | Server |
| Silero VAD | Detects when I start and stop speaking | Server (inside Pipecat) |
| openWakeWord | Detects "Hey Jarvis" on my device; audio leaves the device only after it fires | Mac (in the Jarvis tab), or the server laptop (headless helper) |
| Echo cancellation | Stops Jarvis hearing its own voice: the browser's built-in `echoCancellation`, or PipeWire's echo-cancel module for the server-laptop helper (SEC-68) | Browser, server laptop |
| sentence-transformers 6.2 | Runs the embedding and reranker models | Server |
| vLLM 0.33 (optional) | Learning high-throughput model serving; needs Linux and an NVIDIA GPU | Server |

### 5.4 Local models

| Model | Job | Runs on |
|---|---|---|
| Gemma 4 E4B, **only if it passes the fit test**; otherwise Gemma 4 E2B (4.6 GB) or Qwen3.5-4B (about 3.3 GB, thinking off) | Daily worker: tags, summaries, facts, MCQ wording, feedback text | Server GPU. The Mac gets E2B |
| Qwen3.5-4B (spare voters: Granite 4.2 3B, Nemotron 3 Nano 4B) | Checker from a different model family | Server GPU |
| Gemma 4 12B (alternative to blind-test: Qwen3.5-9B) | Night writer: deep dives, explanations, foundation pages | Server (GPU + RAM) |
| BGE-M3 (to test against Granite Embedding 311M R2 and Harrier-OSS-v1 0.6B on Hindi and Telugu) | Search by meaning (multilingual), relevance filter, duplicate detection | Server GPU or CPU; Mac |
| bge-reranker-v2-m3 (alternative: Qwen3-Reranker-0.6B) | Puts the best search results first | Server GPU or CPU |
| Whisper large-v3-turbo (accuracy fallback: Whisper large-v3; English-only live mode: Parakeet-TDT-0.6B-v3) | Word-for-word transcripts; fillers need a test | Server (Mac backup) |
| Kokoro-82M (optional: Indic Parler-TTS for an Indian-English, Hindi or Telugu voice) | Spoken feedback and shadowing sentences | Server / Mac |
| wav2vec2-lv-60-espeak-cv-ft (challenger: POWSM CTC) | Hears which sounds I actually said | Server GPU |
| RapidOCR via Docling; Qwen3.5-4B for handwriting and maths (extras: Granite-Docling-258M, PaddleOCR-VL-1.6) | Text from screenshots, PDFs and handwritten notes; maths checked with SymPy | Server; Mac |
| Llama Prompt Guard 2 (86M) or ProtectAI's DeBERTa-v3 prompt-injection model (test both on my own news and books; check the licence first) | Injection check in the Intake Gateway | Server CPU (parser sandbox) |
| openWakeWord "hey jarvis" | Wake word | My device's CPU |

- **Jarvis uses the worker model:** routing and replies use Qwen3.5-4B with thinking off, already loaded, so the fast path needs no model swap.
- **Fine-tuning is a later option only:** a LoRA adapter trained on my approved answers, after about 6 months of feedback data ([06](06_Improvements.md) B8).

**Research findings (checked 2026-11-07, see [03_Local_Models_Research.md](03_Local_Models_Research.md); old-vs-new summary in [04_Old_vs_New_SLMs.md](04_Old_vs_New_SLMs.md)):**
- **Gemma 4 E4B is too big for 6 GB in Ollama.** I checked the Ollama tags page: Q4_K_M is 6.6 GB and QAT is 6.1 GB. The "E" models store about 8B parameters, and 4.5B of them are effective. Google's official QAT GGUF is 5.15 GB for llama.cpp. Test the fit before choosing it; the fallback is E2B or Qwen3.5-4B.
- **gpt-oss 20B is dropped for the 16 GB plan.** Ollama lists it at 14 GB, against 6 GB of VRAM plus 6–8 GB of free RAM. Gemma 4 26B A4B is the better target after a 32 GB upgrade.
- **Whisper may drop "um" and "uh".** No model card promises to keep them. The plan is to test an `initial_prompt` that contains fillers, and to keep Whisper large-v3 for scored sessions.
- **Hindi and Telugu:** Granite Embedding R2 311M is the only embedding card that names both. Kokoro has no Indian-English voice.
- **Licence and safety traps:** jina-reranker-v3 and ZIPA are non-commercial; Piper is GPL-3.0; Nemotron uses NVIDIA's own licence; AI4Bharat's IndicConformer needs `trust_remote_code`, which breaks the security rule in section 8.1, so it stays out unless it runs in a sandbox.
- **Qwen models have no official GGUF.** Use unsloth or lmstudio-community builds and check the file hash. Google, IBM, NVIDIA and ggml-org publish official GGUF files for some models.
- **Unverified in the research:** the Gemma 4 release date (2026-04-02) comes from a secondary source, the MTEB and Open ASR leaderboards showed no data, and the memory figures marked "estimate" are arithmetic, not measurements.

**Settings that make the RTX 3060's 6 GB work:**
- One model loaded at a time (`OLLAMA_MAX_LOADED_MODELS=1`).
- An 8k context for daily jobs.
- `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` to shrink the memory the context uses.
- 4-bit (Q4_K_M or QAT) models; avoid 2–3-bit versions, where quality drops.
- A model file bigger than about 5 GB won't sit comfortably in 6 GB of VRAM, because the context cache and CUDA buffers need room too.
- Qwen3.5 models think by default; turn it off for JSON jobs with `chat_template_kwargs: {"enable_thinking": false}`.
- For live voice, a smaller Whisper so Whisper and Gemma fit on the GPU together.

**On the Mac:** run Ollama natively, not in Docker (Docker on a Mac can't use the GPU), and keep model downloads under about 5 GB.

### 5.5 Learning tools (no LLM needed)

| Tool | Purpose | Runs on |
|---|---|---|
| LanguageTool | Grammar and spelling checks | Server (Docker) |
| Montreal Forced Aligner | Lines up my audio with the words, for pronunciation scores | Server |
| parselmouth (Praat) | Pitch and intonation | Server |
| spaCy + wordfreq | Word variety; picks new and advanced words from my reading | Server |
| py-fsrs | Flashcard and revision scheduling (the method built into modern Anki); its optimizer fits my own forgetting curve after about 1,000 reviews | Server |
| SymPy | Checks maths answers | Server |

### 5.6 Getting data from the internet

| Tool | Purpose | Runs on |
|---|---|---|
| feedparser | RSS feeds: news, PIB, RBI, blogs, YouTube channels, GitHub releases | Server (fetcher container) |
| httpx | Official APIs: Wikipedia, PyPI, npm, Maven, Hacker News, arXiv, World Bank, IMF, FRED, data.gov.in | Server (fetcher container) |
| trafilatura | Pulls clean article text out of a web page | Server (parser container) |
| Crawl4AI | Only for pages that need a real browser. Optional and heavy | Server (sandbox) |
| Docling 2.146 + RapidOCR | PDFs (cutoffs, budget, NCERT, whole books in 25-page parts) and text from images | Server (parser, no network) |
| ffmpeg + ffprobe | Audio and frames from videos I add; checks video containers (`-protocol_whitelist file`, no playlists) | Server (parser, no network) |
| Starter packs | Official and open exam material listed in `infra/sources/exam_packs.yaml`, downloaded once after I approve the list | Server (fetcher, through Squid) |
| Apple text recognition (ocrmac) | Text from screenshots (backup) | Mac |
| changedetection.io | Watches exam websites for new notifications | Server (Docker) |
| SearXNG | Private web search for filling gaps and fact-checks | Server (Docker) |
| Kiwix (optional) | Offline Wikipedia | Server |

### 5.7 Interfaces

| Tool | Purpose | Runs on |
|---|---|---|
| **Jarvis** | The main way to use the app: one voice assistant for news, questions, tutoring, quizzes, the plan, the library, exams, progress, English coaching and server status (section 5.15) | Server (brain and voice); my devices (wake word, microphone, speaker) |
| Telegram bot (python-telegram-bot) | Briefings, quizzes, voice notes, alerts, approvals, sending links and files | Bot on the server; Telegram app on phone and Mac |
| Obsidian | Reading and browsing notes | Mac, phone |
| **Next.js web app** | The screens: Today, Ask, Library, Practice, Jarvis, Exams, World, Progress, Models, My profile, Security, Settings (see section 5.14) | Server (Docker); opened in a browser on the Mac or phone over Tailscale |
| Claude Code + FastMCP 4 vault server | Claude reads my notes while I code (read-only) | Mac |

### 5.8 Plugins and extensions

| Plugin | Purpose | Runs on |
|---|---|---|
| Obsidian Bases (built in) or Dataview (community) | Tables inside notes: syllabus coverage, glossary index | Mac, phone |
| Templater (community) | Templates for foundation pages, deep dives, STAR stories | Mac |
| Obsidian Canvas (built in) | Cause-and-effect chains, mind maps | Mac |
| Obsidian Web Clipper (official browser extension) | Saves articles I'm reading | Mac browser |
| My own FastMCP server | Gives Claude Code search and read access to the vault. No writing | Mac |
| Apprise (inside changedetection.io) | Sends exam alerts to Telegram | Server |

### 5.9 Connectivity

| Tool | Purpose | Runs on |
|---|---|---|
| **Tailscale** | Private, encrypted network between the server, Mac and phone. Nothing is opened to the internet. Tailnet Lock is on, so a new device needs a signature from one of my own devices (alternatives in section 11) | All devices |
| **Tailscale Serve** | The only door into the server: HTTPS for the web app (browsers need HTTPS for the microphone, and it tells the app who is signed in) and the `/voice` path for live voice signalling | Server |
| **Tailscale SSH** | Admin access to the server from the Mac without opening port 22 | Server |
| **Syncthing** | Copies the vault directly and encrypted between the server, Mac and Android, and delivers the Library folder (big PDFs and videos) to the server, which only receives it | Server, Mac, Android |
| **Unix socket** | `voice-live` reaches the API through a socket file, not a network port (Jarvis turns) | Server |
| **Alerter bot** | Security alerts and the daily heartbeat, with its own bot token, sent from the host | Server → Telegram |
| **Telegram Bot API (long polling)** | The bot asks Telegram for new messages, so no incoming port is needed | Server → Telegram |
| **WebRTC** | Audio for live voice practice | Browser ↔ server |
| **Docker networks** | Keep services apart: database on an internal network, parser with no network at all | Server |
| **Squid (outbound proxy)** | Fetchers can reach only allowlisted websites, and never the home network | Server (Docker) |
| **MCP (stdio)** | Claude Code talks to the vault server on the same Mac | Mac |
| **OpenTelemetry** | Sends traces to Langfuse | Server |

### 5.10 Testing and monitoring

| Tool | Purpose | Runs on |
|---|---|---|
| DeepEval 4 | Tests MCQ correctness and tagging accuracy | Server (weekly, with local models) |
| Ragas | Tests search quality | Server (weekly) |
| promptfoo | Prompt-injection tests with poisoned pages, PDFs and video transcripts, including commands aimed at Jarvis | Server; in CI with a fake model |
| Langfuse v4 | Traces every model call. It's heavy, so it starts only when needed | Server (Docker, on demand) |
| Telegram failure alerts | The bot tells me when a job fails. Security alerts come from the separate alerter (section 5.17) | Server |
| Vitest + Testing Library | Tests for UI components | Mac, CI |
| Playwright + axe | End-to-end tests of every screen (the voice screen with a fake microphone) plus accessibility checks | Mac, CI |

### 5.11 Security tools

| Tool | Purpose | Runs on |
|---|---|---|
| gitleaks (pre-commit hook) | Blocks committing passwords and tokens | Mac, CI |
| pip-audit + Dependabot | Warn about Python and npm packages with known vulnerabilities | CI, GitHub |
| `check_deps.py` + `approved_deps.yaml` | CI fails on any direct dependency I haven't approved, which catches made-up and look-alike package names (SEC-52) | CI |
| `vet_package.py` | Before I approve a package: its age, look-alike names, downloads, source repository and known vulnerabilities | Mac |
| `check_mcp.py` | CI fails if a committed MCP config lists a server that isn't on the `AGENTS.md` allowlist or isn't pinned (SEC-53) | CI |
| `check_skills.py` | CI fails if a skill in the repo, or a plugin that a committed agent setting enables, isn't on the `AGENTS.md` allowlist, or if a listed skill's files changed (SEC-53) | CI |
| uv `exclude-newer` | A delay for brand-new Python package versions, like pnpm's 24-hour wait | Mac, Docker builds |
| Renovate (or Dependabot) | Opens a pull request when a new version or image digest appears; Trivy scans it before I merge (SEC-55) | GitHub |
| cosign (optional) | Checks image signatures where the publisher provides them | CI |
| pnpm 11 safety settings | Waits 24 hours before installing newly published package versions; only allowed packages run install scripts | Mac, Docker builds |
| Trivy | Scans Docker images for known vulnerabilities | CI, server |
| restic | Encrypted backups to an external drive | Server |
| unattended-upgrades (or dnf-automatic) | Installs security updates automatically | Server |
| ufw (or firewalld) | Firewall that blocks all incoming connections | Server |
| AppArmor (or SELinux) | Limits what each program and container may do | Server |
| LUKS / FileVault | Full-disk encryption | Server / Mac |
| Gatekeeper + XProtect | Built-in malware protection | Mac |

### 5.12 Optional cloud (off by default)

| Service | Purpose | Rule |
|---|---|---|
| Azure AI Speech | More accurate pronunciation scores | Practice audio only |
| Claude API (Haiku 5.5, Sonnet 5.5) | Backup for the weak spots | Public text only, with a budget cap in LiteLLM |

### 5.13 Shared with LifeLedger

- **Same Linux server, Ollama and Langfuse.**
- **Same Postgres server,** but separate databases and separate database users.
- **A separate Telegram bot for each project,** so a leaked token exposes only one.
- **Temporal stays LifeLedger-only.** This project doesn't need it.

### 5.14 Frontend: the Next.js web app

The screens of the app on my laptop and phone; Jarvis (section 5.15) is the voice side, and an orb button on every screen opens it. The web app replaces Streamlit, because I want a professional UI and UX. Telegram stays for push messages (briefing, alerts, quick voice notes), and Obsidian stays for reading notes.

#### Frontend stack

| Tool | Purpose | Notes |
|---|---|---|
| Next.js 16 (App Router) + React + TypeScript | The web app: pages, server rendering, API routes | Developed on the Mac; runs on the server in Docker |
| Tailwind CSS v4 + shadcn/ui | Design system: colours, spacing, typography, dark and light mode | shadcn copies component code into the repo, so I own it and depend on fewer packages |
| Radix UI (inside shadcn/ui) | Accessible building blocks: keyboard use, focus, screen readers | |
| Vercel AI SDK 7 (`useChat`) | Streams answers onto the page as they're written | Connected to FastAPI through the web app's own API routes |
| AI Elements + Streamdown | Chat and answer components; Markdown that renders cleanly while it's still streaming | Plugins `@streamdown/math` (KaTeX formulas for GATE) and `@streamdown/mermaid` (diagrams) |
| shadcn charts (Recharts) | Economy dashboard, progress, mock analysis, voice trends | Same look as the rest of the app |
| Motion | Smooth page and card transitions | Turns itself down when "reduce motion" is on |
| ElevenLabs UI Orb (MIT, shadcn-compatible) | 3D orb that reacts to sound and shows idle, listening and talking | Built on Three.js (React Three Fiber + drei); used only as a UI component, fed by my own audio levels |
| Pipecat Voice UI Kit + React client + SmallWebRTC transport | Connects the browser to the Pipecat voice server; mic controls, connect button, voice visualiser | Signalling through `/api/offer`; audio flows directly over Tailscale |
| Web Audio API (built into browsers) | Measures the live volume and frequencies of my voice and the coach's voice | Drives the orb and waveforms |
| wavesurfer.js | Plays session recordings as waveforms, with fillers and mispronounced words marked | |
| next-themes, lucide-react, sonner, cmdk | Dark mode, icons, toast messages, ⌘K command palette | Small, widely used packages |
| TanStack Query | Caches data and keeps screens fresh | |
| openapi-typescript + Zod | TypeScript types generated from FastAPI's API schema, so frontend and backend always agree | |
| Web app manifest | Installs the app on the phone's home screen | HTTPS comes from Tailscale Serve |

#### Screens

| Screen | What it shows |
|---|---|
| **Today** | The briefing as cards by section, each with "why it matters" and "how it affects me", exam tags, my one-line take, today's plan and the energy check-in |
| **Ask** | Chat with my brain: streaming answers with sources, formulas, tables and diagrams; "save to vault"; 👍/👎 and other feedback buttons |
| **Library** | My books, PDFs and videos: processing status, chapters, chapter summaries, "Mark chapter as read", "Ask this PDF", "show source" at the exact page or video moment, and "Add file": an upload that goes through the Intake Gateway like a file from the Library folder |
| **Practice** | MCQs with a timer and instant explanations, flashcard reviews (10 new and 40 reviews a day by default), speed maths, typing practice, the mistakes notebook |
| **Jarvis** | The orb, live captions, practice sessions started by voice (interviews, group discussions, read-aloud, shadowing) and English coaching reports |
| **Exams** | Syllabus coverage map (with topics that have no source yet), the sources linked to each topic, starter packs, mock analyser, revision calendar (+1, +7, +30, +90), exam alerts, final 30 days mode |
| **World** | Economy dashboard, story timelines, deep dives, glossary, forward fact-checker |
| **Progress** | Study time per goal against plan, energy patterns, streaks, weekly review |
| **Models** | Live GPU and memory use, which model does each job, switching and testing models, downloading or deleting models, change history and rollback (see "The Models screen" below) |
| **My profile** | Everything the app has learned about me: style rules per mode, topic levels, weights and liked examples, each editable or deletable; the weekly improvement report with approve, ignore and undo |
| **Security** | Open alerts and their history, containment status, the daily heartbeat, the Lynis score trend, and the Quarantine list (why each item is held; release or delete) |
| **Settings** | Sources, local or cloud models, budget, privacy (delete recordings), daily card limits, my English practice time, quiet hours, wake-word mode |

#### How answers look

- **Structured, not walls of text.** The backend returns Pydantic objects, so the web app shows each answer as the right component: an explainer with four sections (what happened, why, what changes, how it affects me), a quiz card, a chart, a timeline or a cause-and-effect diagram.
- **Streaming:** text appears as it's written, with a skeleton placeholder until the first words arrive.
- **Rich formatting:** headings, tables, KaTeX formulas, highlighted code and Mermaid diagrams.
- **Trust signals:** every answer shows its sources as chips, a *verified* or *unverified* badge, and which notes it used.
- **Actions:** copy, save to vault, make flashcards, ask a follow-up.
- **Quality bar:** dark and light mode, keyboard shortcuts, a phone-first layout, accessible colours and focus states, and a clear empty, loading or error state on every screen.

#### The Jarvis screen

```
┌───────────────────────────────────────────────┐
│ Jarvis · mock interview · 04:12  ● Listening  │
│                                               │
│                 (  3D ORB  )                  │
│     idle · listening · thinking · talking     │
│                                               │
│        ▁▂▅▇▅▂▁▂▅▇▅▂▁   my voice, live         │
│                                               │
│ Jarvis: "Why did you choose Temporal?"        │
│ Me:     "Because it can wait for weeks and…"  │
│                                               │
│ [ Mute ]        ( mic )       [ End session ] │
└───────────────────────────────────────────────┘
```

- **No modes to pick:** I just talk ("Interview me for SBI", "Quiz me", "What's new?"), and Jarvis starts the right session.
- **Wake-word mode:** while the Jarvis tab is open on the Mac, "Hey Jarvis" starts a turn. A listening light shows whenever audio is going to the server, and the mute switch stops the microphone.
- **Confirmations:** when Jarvis asks "Shall I…?", the screen shows the exact change with a 10-second countdown, plus a Confirm button that stays valid for 60 seconds (SEC-56).
- **The orb shows Jarvis's state and moves with the real sound:** it breathes when idle, reacts to my voice while listening, and pulses with Jarvis's voice while it speaks. The ready-made orb already handles idle, listening and talking; I add a "thinking" state.
- **My voice** appears as a live waveform from the microphone.
- **Live captions** for both voices. Corrections still wait until the end, as the Voice Coach design rules say.
- **Read-aloud mode:** each word lights up as I read it. Afterwards every word is coloured green, amber or red by its pronunciation score; tapping a word plays the correct version next to mine.
- **Shadowing mode:** my pitch curve drawn over the coach's, to show where my intonation differs.
- **Session report:** my recording as a waveform with fillers and mispronounced words marked, grammar fixes shown as before and after, and trend charts for fillers per minute, speaking speed and pronunciation score.
- **How it moves "as in real":** the Web Audio API measures the volume and frequencies of both audio streams about 60 times a second and feeds them to the orb and waveforms. Pipecat's events (who is speaking, live transcripts) switch the states and fill the captions.
- **Smooth on every device:** a simple 2D circle when "reduce motion" is on or the phone struggles with 3D; animation pauses when the tab is hidden.

#### The Models screen

One place to see and control every local model from the web app, instead of the terminal.

```
┌──────────────────────────────────────────────────────┐
│ Models                  Server ● online   Mac ● on   │
│ GPU  RTX 3060  ████████░░  4.1 / 6 GB   61 °C        │
│ RAM            ██████░░░░  9.8 / 16 GB               │
├──────────────────────────────────────────────────────┤
│ Job           Model              Where     Status    │
│ Worker        Qwen3.5-4B         GPU       ● loaded  │
│ Checker       Gemma 4 E2B QAT    GPU       ○ idle    │
│ Night writer  Gemma 4 12B QAT    GPU+RAM   ◷ 1–5 am  │
│ Embeddings    BGE-M3             GPU       ● loaded  │
│ Speech        Whisper turbo      GPU       ○ idle    │
├──────────────────────────────────────────────────────┤
│ [ Change ]  [ Run test ]  [ Compare ]  [ Add model ] │
└──────────────────────────────────────────────────────┘
```

**What it does**
- **Live status:** whether the server and the Mac are online, GPU memory, temperature and RAM, which models are loaded right now, and the speed (tokens per second) of recent jobs.
- **One row per job:** worker, checker, night writer, embeddings, reranker, speech to text, text to speech, pronunciation and vision. Each shows its model, its backup and the machine it runs on.
- **Change a job's model** from a dropdown of approved models. Before switching, a **fit check** says "fits on the GPU", "needs RAM" or "doesn't fit", from the file size and the context length. The checker must stay a different family from the worker, and the screen blocks a change that breaks this rule.
- **Test bench:** run a job's test set on a candidate (for example 50 MCQs, 100 tagged news items, or filler-word clips) and see accuracy, speed and peak GPU memory next to the current model. The night writer gets a blind A/B vote. A model only takes over a job after passing its test gate.
- **Playground:** try a prompt on any model with thinking on or off, a chosen context length and temperature. Nothing is saved.
- **Model library:** installed models with size, 4-bit type, licence, family and last use. Unused ones can be deleted.
- **Add a model** from the approved list only, with a download progress bar, the licence shown first, and a free-disk check.
- **Load and unload:** a "free the GPU" button before voice practice, and the night window for the 12B.
- **Backups:** turn the Mac backup on or off per job; the cloud backup stays off unless I turn it on, with its monthly spend shown.
- **History and rollback:** every change is logged (date, old and new model, test score), with one-click rollback.
- **Alerts:** a toast and a Telegram message when a model fails to load, the GPU memory is full, or a test score drops.

**How it works**
- Next.js calls a FastAPI "models" API. FastAPI talks to Ollama's API on the server and the Mac (`/api/tags` for installed models, `/api/ps` for loaded ones, `/api/pull` to download, `/api/delete` to remove, `/api/show` for details).
- GPU numbers come from NVIDIA's monitoring library (NVML, through `nvidia-ml-py`).
- The job-to-model map lives in Postgres. When it changes, the backend updates LiteLLM's routes, so the rest of the app needs no change.
- Tests run as queued jobs (DeepEval for the language models), and live status reaches the page through server-sent events.
- Speech, voice and pronunciation models are files rather than Ollama models. The backend manages them in the same list, with the same approved-list rules.

**Safety rules for this screen**
- Downloading, deleting and switching models need my Tailscale identity and a confirm step.
- The browser never talks to Ollama directly; Ollama stays bound to `127.0.0.1`.
- Downloads come only from the approved list: official Ollama library models and approved Hugging Face organisations, in GGUF or safetensors format. No pickle files (`.pt`, `.bin`) and no `trust_remote_code`.
- One download at a time, with a size limit and a free-disk check.

#### How the web app talks to the backend

- **The browser talks only to Next.js.** Next.js calls FastAPI on the internal Docker network, so FastAPI and Postgres are never exposed.
- **Answers stream** from LangGraph through FastAPI (server-sent events in the AI SDK's stream format) to `useChat`.
- **Voice:** the browser connects to the Pipecat voice server with WebRTC. Signalling goes through Tailscale Serve's `/voice` path; the audio flows directly over Tailscale. Jarvis turns go from the voice server to the API through a Unix socket, never a network port.
- **Shared types:** TypeScript types are generated from FastAPI's API schema.
- **Alternative:** AG-UI (with CopilotKit), the open agent-to-UI protocol from the stack doc, is worth trying later if I want it on my resume.

#### Web app security

- **Reachable only through Tailscale Serve (HTTPS).** The app also checks Tailscale's identity headers to confirm the request comes from me.
- **No secrets in the browser:** no API keys in client code or `NEXT_PUBLIC_` variables.
- **Answers are rendered as Markdown only,** never raw HTML, so injected text can't run scripts.
- **External images in answers are blocked** by the Content Security Policy. Otherwise a poisoned page could make an answer load an image link that carries my data out.
- **Links in answers** open in a new tab with `rel="noopener noreferrer"`.
- **Security headers:** a Content Security Policy, and no embedding in other sites (`frame-ancestors 'none'`).
- **Model admin actions** (download, delete, switch) need my identity and a confirm step, and downloads come only from the approved list.
- **Microphone only while Jarvis is active** (orb tapped, or wake-word mode on in the Jarvis tab), with a visible listening light and a mute switch; recordings follow the Voice Coach privacy rules.
- **Unknown hosts refused:** every request's `Host` header must be the app's own name, which blocks DNS rebinding (SEC-51).
- **Cross-site requests blocked (SEC-54):**
  - `GET` never changes data.
  - Every request that changes data must come from the app's own origin and carry the app's custom header.
  - Cookies, if any, use `SameSite=Strict`, `HttpOnly` and `Secure`.
- **Confirm steps use one-time tickets:** valid for one exact action, once, and only for a short time (SEC-56).
- **Feedback counts only from my signed-in session** (SEC-49).
- **npm supply chain:** pnpm 11 waits 24 hours before installing newly published package versions (`minimumReleaseAge`), only allowed packages may run install scripts (`allowBuilds`), the lockfile is committed, and Dependabot watches npm packages too.

**Checked 2026-11-07:** [ElevenLabs UI](https://elevenlabs.io/blog/elevenlabs-ui), [Pipecat Voice UI Kit](https://voiceuikit.pipecat.ai/), [Streamdown](https://github.com/vercel/streamdown).

### 5.15 Jarvis: the voice assistant

**What it is:** one voice assistant, the main way I use the app. I talk, and Jarvis picks the right job: news, questions, tutoring, quizzes, my plan, the library, exams, progress, English coaching or server status. Details and decisions are in [06_Improvements.md](06_Improvements.md) Part C, and the flow is in [05_Architecture.md](05_Architecture.md) §7.17.

| Part | Tool | Runs on |
|---|---|---|
| Wake word | openWakeWord's "hey jarvis" model | Mac: in the Jarvis tab (an in-browser model; to confirm in the build plan). Server laptop: an optional headless helper, since the server has no browser (SEC-51) |
| Microphone and speaker | Browser WebRTC with echo cancellation; PipeWire echo-cancel for the helper | My device |
| Audio pipeline | Pipecat, Silero VAD, faster-whisper (live model), Kokoro, an echo filter, barge-in | Server (`voice-live`) |
| Brain | Intent router (Qwen3.5-4B with JSON output), skills, one-time confirmation tickets, conversation memory | Server (`jarvis`, reached through the API's Unix socket) |
| Phone | Tap the orb; a phone wake word needs a native app later | Phone |

**Rules:**
- **What it may do:** Read runs at once; Write (inside the app only) needs my spoken "yes" within 10 seconds; Never-level actions have no tool at all (SEC-45, SEC-46, SEC-56).
- **English coaching is off by default:** it starts when I ask, or at my set practice time. Normal conversations aren't analysed.
- **It greets and suggests:** when I open the app, Jarvis speaks first with at most 3 suggestions. Urgent alerts also come through Telegram.
- **English only;** a calm British male voice *style* from Kokoro, not a copy of any real actor's voice.
- **Speed:** simple replies in about 1–2 seconds (estimate). Hard questions get "Let me think about that" and go to the night model.
- **The GPU is shared:** a Jarvis session takes the GPU lease, and other model jobs wait.
- **It doesn't hear itself:** echo cancellation; the wake word is ignored while Jarvis speaks; its own words are dropped from transcripts (SEC-68).

### 5.16 Intake Gateway: one door for all incoming data

**What it is:** every input passes the Intake Gateway before anything else touches it. It runs inside the parser sandbox: no network, no secrets, fixed limits. Details are in [06_Improvements.md](06_Improvements.md) Part F.

| Step | Tool | Notes |
|---|---|---|
| Real file type | libmagic (`python-magic`) | By content, never by extension; mismatches, polyglots and archives rejected |
| PDF structure | pdfid | JavaScript, auto-actions, launch actions, embedded files |
| Office macros | oletools (`olevba`) | Macros mean quarantine |
| Video containers | ffprobe (`-protocol_whitelist file`) | Playlists rejected |
| Antivirus | ClamAV (`clamd`) in its own no-network container, reached through a Unix socket; signatures from `freshclam` in the edge zone through Squid | Fails closed if the signatures are more than 3 days old |
| Rules | YARA (`yara-python`) | My own rules in `infra/intake/` |
| Rebuild | Docling and RapidOCR, Pillow re-encoding; for flagged documents, pages rendered to images (pypdfium2) and OCR'd | The original file structure is thrown away (the approach Dangerzone uses) |
| XML | defusedxml | No external entities or DTDs (SEC-54) |
| Text cleaning | Our `security/text.py` | Invisible characters removed, Unicode normalised, HTML stripped |
| Injection check | Llama Prompt Guard 2 or a DeBERTa classifier, plus pattern rules | CPU |
| Links | Our `security/urls.py` | Extracted, never followed |

**The verdicts:**
- **Pass:** goes on to the normal pipeline.
- **Flag:** readable, but never a fact source, MCQ or card.
- **Quarantine:** held for 7 days; I release or delete it.
- **Reject:** dropped and logged.

### 5.17 Detection and response

**What it is:** alarms for when something gets through, and automatic containment. Details are in [06_Improvements.md](06_Improvements.md) Part H.

| Tool | Watches | Runs on |
|---|---|---|
| Falco | Inside containers in real time: shells, unexpected programs, connections outside allowed peers, secret reads, writes, new root processes. Alerts go to a JSON file that the alerter follows | Host (systemd, eBPF driver) |
| auditd | Secrets, honeytokens, the Docker socket, sudoers, SSH keys; every sudo and login | Host |
| AIDE | Host files, nightly | Host |
| Integrity checker (ours) | `docker diff` and running image digests vs the pins, nightly | Host timer |
| Resource watcher (ours) | GPU and CPU use vs the job schedule (NVML), restart loops, outbound bytes | Host |
| pgaudit | Database roles, permissions, structure changes, honeytoken reads, failed logins | Postgres |
| Squid deny log | Blocked outbound requests | Edge zone |
| Lynis | Monthly hardening score | Host |
| Alerter (ours) | Sends alerts and the daily heartbeat with its own bot token; keeps an append-only log | Host |
| Honeytokens | Fake secrets that nothing uses, so any touch is an attack | Host, Postgres, vault |

**Build order:**
1. Honeytokens, the heartbeat and egress alarms.
2. Nightly integrity checks and database auditing.
3. Falco: alerts only for about two weeks of tuning, then automatic containment.

## 6. Data sources

### Rules

- **RSS and official APIs first.** Scrape a page only when there's no other way.
- **Polite:** follow robots.txt and site terms, one request every few seconds per site, cache results.
- **Personal use only:** keep summaries and links. Full article text is kept only while it's being processed.
- **Safe:** all fetching and parsing happens in the sandbox. Every input passes the Intake Gateway first (section 5.16). Untrusted text goes to the reader (no tools), then a Pydantic check, then the writer.
- **No pirated material, ever:** file-sharing and "free PDF" sites (including Telegram channels sharing coaching books) are never allowlisted. They're illegal and a common way malware spreads. Anything I legally own goes in the Library folder.
- **Licences respected:** NCERT, NIOS, NPTEL and MIT OCW material is for my personal study only, never shared to the study group.
- **Official sources first** for syllabus, answer keys and cutoffs. Weightage from post-exam analyses and "memory-based" bank papers are labelled unverified.
- **New allowlist domains, each added on purpose:**
  - **Exam and study sources:** ncert.nic.in, nios.ac.in, nptel.ac.in, ocw.mit.edu, rbi.org.in, indiabudget.gov.in, pib.gov.in, ibps.in, sbi.co.in, ssc.gov.in, and the year's GATE site.
  - **Antivirus signatures:** database.clamav.net, used only by `clamav-update`.

### Sources

| Area | Where it comes from | How |
|---|---|---|
| India news | RSS feeds of Indian outlets, Google News RSS by topic, PIB (government press releases) | RSS |
| World news | RSS of world outlets, UN News, Wikipedia's "In the news" | RSS, Wikimedia feed API |
| Politics | PRS Legislative Research (neutral bill summaries), Parliament (sansad.in), Election Commission, outlets with different viewpoints | Pages and RSS |
| Economy and finance | RBI press releases, MOSPI (inflation, GDP), data.gov.in, Budget and Economic Survey PDFs, daily gold rates (IBJA), petrol prices (oil company sites), World Bank, IMF and FRED APIs | RSS, APIs, PDFs through Docling |
| Tech | GitHub release feeds, PyPI, npm and Maven APIs, Hacker News API, subreddit RSS, blog RSS, arXiv API | APIs, RSS |
| YouTube | Channel RSS feeds for new-video alerts | RSS |
| X and LinkedIn | Nothing safe to automate. Follow the same people's blogs and newsletters (Substack has RSS) and share posts to the bot by hand | Manual |
| Exams | Official SSC, IBPS, SBI and GATE pages watched by changedetection.io; GATE past papers; SSC answer keys (captured when released, since they're up only briefly); official cutoff PDFs | Page-change watching, PDFs |
| Exam study material | NCERT and NIOS textbooks; NPTEL course notes and lecture transcripts; MIT OpenCourseWare; RBI publications, the Economic Survey, Budget documents and PIB; the year's GATE site, ibps.in, sbi.co.in, ssc.gov.in (the full list per exam is in [06](06_Improvements.md) Part G) | A one-time starter pack after I approve `infra/sources/exam_packs.yaml`, then the exam watcher |
| My own books and videos | Books I've bought, class notes, coaching material I legally have, lecture videos I legally have | The Library folder (Syncthing) |
| Background knowledge | Wikipedia API; optional offline Wikipedia (Kiwix); NCERT textbooks (free PDFs, the standard GK base for SSC and bank exams); Constitution of India (official PDF) | API, downloads |
| Web search | SearXNG (self-hosted search) | Self-hosted |

**YouTube note:** the official API gives video details but not other people's transcripts. An unofficial caption library works for free, but it may break and is a grey area under YouTube's terms. Downloading the audio to transcribe it breaks those terms.

**What I send myself:**
- **Through Telegram:** links, PDFs, screenshots, voice notes and forwarded messages.
- **Web Clipper:** for articles I'm reading on a computer, the Obsidian Web Clipper saves them to the vault's `Clippings/` folder. They're still untrusted and pass the Intake Gateway's text checks before indexing.
- **Library folder:** big PDFs and videos go here (Syncthing), because Telegram bots can't download files over 20 MB. Videos are transcribed locally; no unofficial YouTube caption scraping.

### Pipeline

1. **Collect** every 1–3 hours: RSS feeds, APIs, page watching, plus whatever I send.
2. **Check** at the Intake Gateway: source, size, real file type, structure, antivirus, rebuild, injection and link checks. Pass, flag, quarantine or reject.
3. **Clean** in the sandbox: trafilatura, Docling or text recognition turn everything into plain text.
4. **Filter:** remove duplicates, apply rules, and keep only what matches my syllabus and interests.
5. **Understand** with local models: tags, summaries, facts and the four questions, based only on the source text.
6. **Verify:** 2–3 source rule and the cross-check by a second model family. Flagged content is never a fact source. A newer official fact on the same subject replaces the old one. Anything uncertain is marked "unverified".
7. **Write:** notes go into the vault with source links; MCQs and flashcards go into Postgres.
8. **Deliver:** the Telegram briefing arrives at my chosen time, Jarvis greets me when I open the app, and Syncthing copies the notes to the Mac.

## 7. How things connect

```
INTERNET (news, APIs, exam sites, ClamAV signatures)
      │  outbound only, allowlisted by Squid
      ▼
┌────────────────── LINUX SERVER (TUF A15) ──────────────────┐
│ fetcher ──▶ raw/ ───────────────────────┐                  │
│ Library folder (Syncthing) ──▶ inbox/ ──┴──▶ parser +      │
│                          Intake Gateway (no network)       │
│                                   │                        │
│ LangGraph workers · jarvis ◀── LiteLLM ──▶ Ollama (GPU)    │
│ Postgres + pgvector (internal network only)                │
│ Telegram bot ── long polling ──▶ Telegram ◀── my phone     │
│ Next.js web app ──▶ FastAPI (internal network only)        │
│      ▲ Tailscale Serve (HTTPS) ◀── Mac and phone browsers  │
│ voice-live ◀── WebRTC audio over Tailscale ── Mac, phone   │
│      └──▶ FastAPI (Unix socket) for Jarvis turns           │
│ vault ◀── Syncthing ──▶ Mac vault ◀── Obsidian, Claude Code│
│ host: Falco · auditd · AIDE · alerter ──▶ alerts bot       │
└────────────────────────────────────────────────────────────┘
```

### Who can reach what

**On Linux, Docker's published ports skip the firewall:** ufw can't block a port that Docker publishes on all addresses. So every container port is bound to `127.0.0.1`, and Tailscale Serve is the only door from my other devices.

| Service | Port | Who can reach it |
|---|---|---|
| Ollama (server) | 11434 | Containers on the internal `llm` network; from phase 9 also `127.0.0.1`, through the no-egress `edge_llm` network, for `voice-live`. Never shared with other devices. Ollama has no password |
| Ollama (Mac) | 11434 | Bound to 127.0.0.1; used only by tools on the Mac (no fallback for server jobs, see 05 D19) |
| Next.js web app | 3000 | My devices, through Tailscale Serve (HTTPS), checked with Tailscale identity headers |
| FastAPI | 8000 | The web app and other containers only; `voice-live` reaches it only through a Unix socket (no port) |
| Pipecat voice server | WebRTC (UDP) | Only over Tailscale: its UDP ports are allowed only on the `tailscale0` interface |
| Postgres | 5432 | Containers on the internal Docker network only |
| LiteLLM | — | Runs as a library inside the worker; no port |
| ClamAV (`clamd`) | — | Its own `clamav` container with no network; only the parser reaches it, through a Unix socket |
| Falco | — | Host only; no network listener (alerts go to a file) |
| Alerter | — | Outgoing connections to Telegram only, with its own bot token |
| changedetection.io, Langfuse | 5000, 3001 (Langfuse moved off 3000) | My devices, through Tailscale Serve only |
| SearXNG, LanguageTool | — | Containers only |
| **Anything** | — | **Never from the internet:** no router port forwarding, no Tailscale Funnel |

## 8. Security: keeping the devices safe

### 8.1 Threats and defences

| Threat | Example | Defence |
|---|---|---|
| Malicious file | A crafted PDF or image attacks the parser | Parser runs in a sandbox: no network, read-only, not root, CPU/memory/process limits, a time limit per job. Parsers kept updated |
| Prompt injection | Hidden text says "delete files" or "send your data" | Reader has no tools; writer never sees raw text; Pydantic checks; Claude Code's vault access is read-only; code from sources is never run |
| Exposed service | Ollama or Postgres reachable from the internet | Every container port bound to 127.0.0.1 (Docker skips the Linux firewall); Tailscale Serve as the only door; no port forwarding; UPnP off |
| Strangers using the bot | Someone finds the bot's username | Bot answers only my chat ID and my study group. Privacy mode stays on in groups, so it sees only commands |
| Stolen token | A bot token or API key leaks through Git | Secrets kept outside Git, gitleaks hook, one bot per project, rotate if leaked |
| Poisoned software | Fake Python package, Docker image or Obsidian plugin | uv lockfile with hashes; pinned image versions (never `:latest`); Trivy and pip-audit; only a few well-known plugins (Obsidian plugins get full access to the computer) |
| Unsafe model file | A `.pt` or `.bin` file runs code when it's loaded | Models only from official sources, in safetensors or GGUF format; `trust_remote_code` off |
| Phishing link | A forwarded message contains a malicious link | Don't open it on the phone. Send it to the bot, which checks it inside the sandbox |
| Knowledge poisoning | A false "fact" gets saved and trusted later | 2–3 source rule, "unverified" label, source recorded on every note, delete everything from one source in one step |
| One project reading another's data | TechRadar code reads LifeLedger's bank data | Separate databases, separate database users with minimum rights, separate Docker networks |
| Runaway job | A job eats all memory or loops forever | Container limits, job time limits, one model at a time, budget caps |
| Account takeover | Someone gets into Telegram, GitHub or Tailscale | Passkeys or 2-step verification everywhere, plus Telegram's cloud password and Tailnet Lock (SEC-67). Even with my Telegram, the bot has no delete commands and can't reach the server's settings |
| Lost or stolen laptop | Someone has the disk | Full-disk encryption (LUKS, FileVault), strong password, automatic screen lock, encrypted backups |
| The Windows side of the dual boot | Malware on Windows tampers with the Linux disk or bootloader | LUKS on the Linux side, Secure Boot on, Windows kept updated with Defender on, nothing untrusted run on Windows |
| Telegram privacy | Bot chats are not end-to-end encrypted | No sensitive data through the bot. For private voice practice, use the web app's Voice Coach over Tailscale |
| Script or data leak through an answer | A poisoned page makes an answer include a script, or an image link that carries my data out | Answers rendered as Markdown only (no raw HTML); external images blocked by the Content Security Policy; links open safely |
| Hijacked npm package | A compromised JavaScript package runs code when it's installed | pnpm 11's 24-hour wait for new versions, install scripts only for allowed packages, committed lockfile, Dependabot |
| Malicious video or playlist | A "video" is really a playlist that makes ffmpeg fetch URLs, or a crafted file attacks a decoder | ffmpeg only in the no-network sandbox with `-protocol_whitelist file`, playlist formats rejected, time limits (SEC-44) |
| A stranger's device syncs files in | A device that isn't mine pushes files into the Library inbox | Syncthing accepts only approved device IDs, listens only on Tailscale, discovery and relays off; file type checked by content; quarantine folder (SEC-43) |
| Jarvis tricked into acting | A news item or PDF says "Jarvis, delete everything" | The router sees only my spoken words; fixed skill list; every write needs my spoken "yes"; no tools for messages, purchases, settings or deletes (SEC-45, SEC-46) |
| Always-listening microphone | The laptop's mic is on, waiting for "Hey Jarvis" | Wake word detected on the device; audio only after the wake word and only to my server; listening light and mute switch (SEC-47) |
| Poisoned "learning" | Fake feedback, or a rule that smuggles in instructions | Feedback only from my session or chat ID; rules can only set style; liked examples sanitised and never used as facts (SEC-48, SEC-49) |
| Any poisoned input | A file or page carries an exploit or hidden instructions | The Intake Gateway checks, rebuilds and flags or quarantines it before anything else touches it (SEC-57) |
| Pirated study PDFs | A "free PDF" of a coaching book carries malware | Never downloaded, and those sites never allowlisted; anything I legally own goes through the Intake Gateway (SEC-05, SEC-57) |
| Silent compromise of a container | Malware in a container hides and waits | Falco, AIDE, integrity checks, honeytokens and egress alarms make its moves noisy; critical alerts stop the container after the evidence is saved (SEC-58 to SEC-66) |
| Silenced alerts | An attacker stops the alerts from reaching me | A separate alerter on the host with its own bot token, and a daily heartbeat, so silence is itself a signal (SEC-66) |
| Stolen GitHub or Tailscale login | Phishing for my password | Passkeys, which a fake site can't use; Tailnet Lock blocks new devices; monthly device checks (SEC-67) |
| Jarvis hears itself | Jarvis reads a news item aloud that says "Jarvis, add…" | Echo cancellation, the wake word ignored while it speaks, its own words dropped from transcripts; writes still need my "yes" (SEC-68) |

### 8.2 Checklist for each device

**Linux server (ASUS TUF A15)**
- **Updates:** automatic security updates (unattended-upgrades on Ubuntu, dnf-automatic on Fedora); the NVIDIA driver from the distro's own packages.
- **Firewall:** ufw (or firewalld) denies all incoming connections. Tailscale only makes outgoing connections, so no port needs to be open. The one exception is the voice server's WebRTC UDP ports, allowed only on `tailscale0`.
- **Docker ports:** every published port bound to `127.0.0.1` (for example `"127.0.0.1:3000:3000"`), never plain `"3000:3000"`, because Docker skips ufw.
- **Disk encryption:** LUKS full-disk encryption. It's chosen at install time, so if it's missing, plan a reinstall with encryption or an encrypted data partition before LifeLedger's bank data lands on the server.
- **Accounts:** a normal user with sudo; root login disabled. Membership of the `docker` group equals root, so only my user is in it.
- **Remote access:** Tailscale SSH, with no port 22 open. If OpenSSH is used instead: keys only, passwords off, listening only on Tailscale.
- **Program limits:** AppArmor (Ubuntu) or SELinux (Fedora) stays in enforcing mode; Docker's default profile then protects every container.
- **Docker rules:**
  - never `--privileged`
  - never mount the Docker socket or the home folder
  - containers not running as root
  - `cap_drop: ALL` and `no-new-privileges`
  - read-only filesystems
  - memory, CPU and process limits
  - log size limits, so logs can't fill the disk
- **Boot:** Linux is the default boot entry and Secure Boot stays on if the distro supports it with the NVIDIA driver. Keep a Linux USB stick for recovery: a Windows update has broken dual-boot Linux before (the 2024 SBAT update).
- **BIOS/UEFI:** set an admin password, so nobody can change the boot order or turn off Secure Boot.
- **No web browsing on the server:** a web page opened there could reach local services through DNS rebinding (SEC-51). The server boots to text mode (`multi-user.target`), so no desktop or browser runs there. Use the Mac or phone instead.
- **Intrusion detection (section 5.17):**
  - Falco: alerts only for the first two weeks, then automatic containment.
  - AIDE nightly, auditd rules, Lynis monthly.
  - The alerter with its own bot token.
  - Honeytokens, kept out of Syncthing, backups and AIDE's scope.
- **Healthchecks:** use exec form (`CMD`), never `CMD-SHELL`, so a shell in a container always means trouble (SEC-58).
- **Syncthing:**
  - only my approved devices
  - listening only on the Tailscale address
  - global discovery and relays off
  - the Library inbox is receive-only on the server
- **The Windows side:** kept updated with Microsoft Defender on, and never used for untrusted downloads, cracked software or game cracks, because it shares the machine. Never mount the Linux disk from Windows.
- **Jarvis wake word (when built):** detected locally; a visible listening light and a mute switch; echo cancellation on (SEC-68). A helper on the server laptop, if used, runs as my user with systemd sandboxing and can reach only the local voice server.

**Mac**
- **Basics:** macOS updates, FileVault, firewall on, Gatekeeper on, a standard account for daily work.
- **Obsidian:** only a few well-known community plugins.
- **Claude Code:** the vault MCP is read-only; read permission prompts before approving.
- **Browser:** only the official Obsidian Web Clipper.
- **Jarvis:** the Jarvis tab listens for "Hey Jarvis" only while it's open, with a listening light and a mute switch.
- **Library folder:** shared with the server through Syncthing; only files I legally own go in it.
- **Backup:** Time Machine.

**Phone**
- **Basics:** screen lock and system updates.
- **Telegram:** 2-step verification and a passcode lock.
- **Forwards:** don't open forwarded files or links; send them to the bot.
- **Web app:** open it only through Tailscale, and allow the microphone only for it.
- **Jarvis:** tap the orb to talk; the microphone is used only while Jarvis is active.

**Home network**
- **Router:**
  - a strong Wi-Fi password (WPA2 or WPA3)
  - a changed admin password
  - updated firmware
  - **UPnP off** (it can open ports by itself)
  - no port forwarding
- **Tailscale:**
  - approve each device
  - key expiry on
  - access rules so each device reaches only what it needs (the phone can open the web app but not reach Postgres)
  - Funnel off
  - **Tailnet Lock on:** a new device needs a signature from one of my own devices, even if my Tailscale login is stolen
- **Monthly checks:**
  - a scan from the phone or Mac: nothing open on the home network, and only the web app's door over Tailscale
  - Telegram's "Active sessions"
  - the Tailscale device list
  - the Syncthing device list

### 8.3 Accounts, secrets and backups

- **Logins (SEC-67):**
  - **Passkeys** where offered (GitHub, the account used to sign in to Tailscale); a passkey only works on the real website, so phishing gets nothing.
  - **Otherwise an authenticator app;** never SMS codes.
  - **Telegram:** 2-step verification with the cloud password.
  - **Azure or Anthropic,** if used: 2-step verification too.
  - **Recovery codes:** stored offline.
- **Where secrets live:** in a `secrets/` folder or Docker secrets, outside Git, readable only by my user. One token per service.
- **Two bot tokens:** the main bot and a separate alerter bot, so a compromised bot can't silence security alerts.
- **Cloud spending limits (if used):** in the provider's console and in LiteLLM.
- **Rotation:** change tokens every few months, and immediately if one leaks.
- **Backups:**
  - a nightly Postgres dump (without the honeytoken table)
  - the vault copied to the Mac through Syncthing
  - a weekly encrypted copy with restic to an external drive: the database, vault, library (originals and extracted text) and secrets, without honeytokens
  - a test restore once a month

### 8.4 If something goes wrong

**A critical alert (automatic, section 5.17):**
1. **Evidence is saved first:** logs, `docker diff`, Falco events and a filesystem export, encrypted and read-only.
2. **The container is stopped** and disconnected from every network.
3. **I'm alerted,** even in quiet hours.

**Then the runbook:**
1. **Read the evidence:** how did they get in?
2. **Rebuild** the container from its pinned image.
3. **Rotate** every secret that container could see.
4. **Check the data, not just the container.**
   - **Why:** containers are throwaway, but anything planted in the database, the vault or a shared folder survives deleting the container.
   - **How:** look at recent writes from that service (provenance), then delete by source or restore from backup.
5. **Fix the hole:** add a test or rule so the same way in fails next time.
6. **Record** the incident in `docs/security/incidents.md`.

**If the whole machine may be compromised:**
1. **Disconnect** the machine: turn off Wi-Fi and remove it from Tailscale.
2. **Rotate secrets:** Telegram bot tokens (through BotFather, including the alerter's), API keys, Tailscale keys.
3. **Check logs,** including the proxy's blocked-request log and the alert log, for strange outbound traffic.
4. **Rebuild** containers from clean images, then restore Postgres, the vault and the library from backup.
5. **Delete** all notes from a suspicious source in one step, using the source tracking.

**Why evidence comes before destroying:** without it, I never learn how they got in, and they come back the same way.

### 8.5 Fix now

- LifeLedger's `docker-compose.yml` uses `temporalio/temporal:latest`. Pin it to a specific version so an update can't silently change or break it.

## 9. Linux server setup

- **Linux:** an LTS distro. Ubuntu LTS is the easiest path for NVIDIA drivers, Docker and CUDA tools. Linux is the default boot entry.
- **GPU:** the NVIDIA driver plus the NVIDIA Container Toolkit. `nvidia-smi` should show the RTX 3060, inside containers too.
- **ASUS extras:** `asusctl` and `supergfxctl` from the asus-linux project, for the battery charge limit, fan profiles and GPU mode. Hybrid mode works fine for AI jobs.
- **Docker:** Docker Engine with the Compose plugin; no Docker Desktop and no VM. Log size limits in `/etc/docker/daemon.json`.
- **Ollama in Docker with the GPU:**

```yaml
services:
  ollama:
    image: ollama/ollama:0.40.14      # pin an exact version, never :latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:11434:11434"       # needs the no-egress edge_llm network (phase 9); internal networks can't publish ports
    volumes:
      - ollama:/root/.ollama
    environment:
      OLLAMA_MAX_LOADED_MODELS: "1"
      OLLAMA_FLASH_ATTENTION: "1"
      OLLAMA_KV_CACHE_TYPE: "q8_0"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  ollama:
```

- **Start at boot:** `restart: unless-stopped` for containers; Tailscale and Syncthing as systemd services.
- **Power:** pick one option.
  - **Always on:** plugged in; lid close ignored (`HandleLidSwitch=ignore` in logind); battery charge limit around 60–80%; Quiet or Balanced fan profile; no desktop session left running (or boot to text mode with `systemctl set-default multi-user.target`) to free RAM.
  - **Wake for jobs:** let it sleep, and wake it with a systemd timer (`WakeSystem=true`) or `rtcwake`.
- **Network:** Tailscale with Tailscale SSH and Tailnet Lock; Tailscale Serve for the web app (HTTPS) and the `/voice` path; ufw denying all incoming, with the voice server's UDP ports allowed only on `tailscale0`.
- **Text mode:** boot to text mode (`systemctl set-default multi-user.target`); nothing on the server needs a desktop or a browser (SEC-51).
- **Syncthing:** only my approved devices, listening only on the Tailscale address, global discovery and relays off, and the Library folder receive-only on the server.
- **Security services (section 5.17):**
  - Falco with its eBPF driver
  - auditd rules, AIDE and Lynis
  - the integrity checker, the resource watcher and the alerter, as systemd services and timers
  - honeytokens placed at deploy time, never committed
- **BIOS/UEFI:** set an admin password.
- **Optional:** try vLLM with a small 4-bit model to learn production-style model serving. Ollama stays the daily runtime.
- **Then harden it** with the checklist in section 8.2.

## 10. Cost

- **Cloud: ₹0** by default.
- **Electricity:** roughly ₹100–250 a month if the TUF A15 runs all day (rough estimate); much less if it only wakes for jobs.
- **Optional cloud backup:** about $1–2 a month for the weak spots. Azure has had a free monthly speech tier that may cover pronunciation, and weekly deep dives can be written in Claude Code sessions I already pay for.
- **Optional hardware:** a RAM upgrade to 32 GB for the TUF A15.
- **Security tools:** ClamAV, YARA, Falco, AIDE, auditd, pgaudit and Lynis are all free and open source.
- **If I ever switch from Tailscale** to Headscale or NetBird, I'd add a small cloud server, which means a small monthly cost.
- Local-only isn't really about saving money. Its real benefits are **privacy and learning**.

## 11. Open decisions

1. **Linux distro:** which one is installed on the TUF A15? Ubuntu LTS is the easiest for NVIDIA and Docker.
2. **Disk encryption:** is the Linux install encrypted with LUKS? If not, fix it before LifeLedger's bank data lands on the server.
3. **Server time:** Linux on all day, or sleep and wake for jobs? And how often is the laptop booted into Windows, when the server is off?
4. **Strictness:** fully local, or keep the small cloud backup for the weak spots?
5. **Phone:** Android or iPhone? Syncthing works on Android; an iPhone needs another way to sync the Obsidian vault.
6. **RAM upgrade:** move the TUF A15 to 32 GB? It unlocks Gemma 4 26B A4B as the night writer.
7. **Model fit tests:** run the test plan in [03_Local_Models_Research.md](03_Local_Models_Research.md) on the real hardware, starting with Gemma 4 E4B (does it fit 6 GB?) and Whisper's handling of "um" and "uh".
8. **Private network:** Tailscale stays for now. The alternatives, if I want no company in the middle:

   | Option | Open source? | Third party involved? | Router port needed? | Effort |
   |---|---|---|---|---|
   | **Tailscale** (current) | Apps yes; coordination server no | Yes: it sees which device connects and when, not my data | No | Very easy |
   | **Headscale** + Tailscale apps | Yes, fully | No (I run the coordination server) | No, but it needs a small cloud server | Medium |
   | **NetBird** (self-hosted) | Yes, fully | No | Similar to Headscale | Medium |
   | **Plain WireGuard** | Yes | None | **Yes, one UDP port** | Harder |
   | **No remote access** | — | None | No | Easiest, but only on home Wi-Fi |

   **A switch would change:**
   - **HTTPS:** Tailscale Serve → Caddy with internal certificates.
   - **Identity:** Tailscale's identity headers → mTLS client certificates, or an app login with a passkey.
   - **Device rules:** the alternative's own features.
9. **Wake word:** in the Mac's Jarvis tab, as a headless helper on the server laptop, or both? **Decided:** the Mac tab first; the helper is optional (plans, D45).
10. **Injection classifier:** Llama Prompt Guard 2 or a DeBERTa model? Test both on my own news and books for false alarms. **Default:** Prompt Guard 2 86M, compared with the DeBERTa model by `make guard-eval` (D35).
11. **Pixel rebuild:** for every document (safest but slow) or only for flagged ones? **Default:** flagged ones only (D36).
12. **Automatic containment:** stop only the container, or also pause the whole pipeline until I check? And how long to keep evidence folders (for example 90 days)? **Default:** stop only the affected container, and keep the encrypted evidence 90 days (D42).
