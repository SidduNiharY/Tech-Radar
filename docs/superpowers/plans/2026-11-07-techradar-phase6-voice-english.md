# TechRadar Brain Phase 6: Voice Coach v1 and English Practice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Telegram voice notes analysed fully on my server, with a spoken summary and a web report. It covers:
- the transcript
- fillers, pace and word variety
- grammar
- pronunciation by phonemes
- the top 3 fixes

It also adds writing, reading, listening, story-bank and reflection practice, transcription for library videos (D38) and an optional English practice time. It ends with `make gate-6`.

**Architecture:**
- **`voice-worker` service** (GPU, no internet) runs faster-whisper, the wav2vec2 phoneme model with our own CTC forced alignment, and Kokoro (ONNX).
- **Code computes all metrics** and chooses the fixes; the worker model only phrases them.
- **`languagetool`** runs on the internal `tools` network.
- **Audio is deleted 24 hours after analysis** unless I tap "Keep"; reports keep only waveform peaks and word timings.
- **Added 2026-11-08:**
  - **Audio checks:** voice notes get the Intake Gateway's file checks (real type, size, `ffprobe` with `-protocol_whitelist file`) before analysis.
  - **Library videos:** `voice-worker` transcribes the audio of library videos waiting since phase 2c.
  - **Shared GPU helper:** `free_gpu` now comes from phase 2c (`techradar.ops.gpu`).

**Tech Stack:** faster-whisper (CTranslate2), ffmpeg, transformers `Wav2Vec2ForCTC` (torch ≥ 2.6), phonemizer + espeak-ng, numpy, kokoro-onnx (ONNX weights), LanguageTool server, wavesurfer.js.

**Spec:** [01](../../../01_Idea_and_Daily_Use.md) (English and soft skills, Voice Coach: what it listens for, design rules, version 1) · [02](../../../02_Tech_Stack_and_Security.md) §5.3–5.5 · [03](../../../03_Local_Models_Research.md) roles 6–8 and test plan · [overview](2026-11-07-techradar-00-overview.md) D23–D25, D28, D31, D38 · [06](../../../06_Improvements.md) C2 (coaching on demand), F2 (audio checks) · phase 2c (media extraction, `free_gpu`, chapters)

## Global Constraints

- The overview's Global Constraints 1–16 apply.
- **Voice note limits:** up to 300 s and 10,000,000 bytes. Listening audio up to 600 s and 20,000,000 bytes.
- **Models:** baked into the image at pinned revisions; no `.pt`, `.pth`, `.pkl` or `.ckpt` files (D24). Kokoro is the ONNX build. wav2vec2 loads with torch ≥ 2.6 (`weights_only` is the default); safetensors is preferred if available. `HF_HUB_OFFLINE=1`.
- **Audio decoding** uses `ffmpeg` through a list of arguments (never a shell) with a 60 s timeout.
- **Design rules from 01:** at most 3 fixes per session; corrections come after the session, never mid-speech.
- **Coaching on demand (06 C2):** only voice notes I send and sessions I start are analysed.
- **Audio intake (SEC-57):** `audio/ogg` by content (`OggS`) and `ffprobe` format `ogg`; anything else gives `I can only analyse Telegram voice notes.`
- **LanguageTool** language `en-GB` (D31).
- **First voice note** gets a one-time notice: `Voice notes pass through Telegram's servers. For private practice, use the Voice screen in the web app (phase 9).`

## Review Focus

1. **A voice note that's silent or almost silent** gives "I couldn't hear speech in that note.", not invented text. Task 2 `test_silence_gives_no_speech`.
2. **A voice note longer than 5 minutes** is refused before download. Task 1 `test_voice_too_long_refused`.
3. **A normal Indian-English accent** shouldn't flag more than about 10% of words. Task 10 eval with a calibrated `FLAG_THRESHOLD`.
4. **Two voice notes sent back to back** are processed one at a time (queue `voice`, concurrency 1) without running out of GPU memory. Task 6 `test_voice_job_frees_gpu_first`.
5. **The audio file is gone 24 hours after analysis** unless I kept it. Task 6 `test_audio_deleted_after_24h_unless_kept`.

Also pinned on 2026-11-08:
- **A voice note that's really another file type** is refused before analysis. Task 1 `test_non_ogg_voice_refused`.
- **A library video waiting since phase 2c** becomes ready with timed chapters. Task 2b `test_video_becomes_ready_after_transcription`.

---

### Task 1: Voice note intake

**SEC:** SEC-15, SEC-26

**Files:**
- Create: `src/techradar/voice/__init__.py`, `src/techradar/voice/intake.py`, `src/techradar/db/migrations/versions/0008_voice.py`
- Modify: `src/techradar/bot/main.py` (voice handler), `compose.yaml` (the `bot` mounts `./data/voice` read-write)
- Test: `tests/voice/test_intake.py`

**Interfaces:**
- Produces:
  - **Migration `0008_voice`:**
    - `voice_sessions` (`id`, `source` text, `created_at`, `duration_s` real, `status` text (`queued`, `analysed`, `failed`, `no_speech`), `audio_path` null, `kept` bool default false, `delete_after` timestamptz null, `peaks` jsonb null, `transcript` jsonb null)
    - `voice_metrics` (`session_id` primary key, `words_per_min`, `filler_count`, `fillers_per_min`, `filler_breakdown` jsonb, `long_pauses`, `avg_sentence_words`, `type_token_ratio`, `overused` jsonb)
    - `pronunciation_scores` (`id`, `session_id`, `word`, `start_s`, `end_s`, `score`, `flagged`)
    - `writing_feedback`, `stories`, `story_drafts`, `listening`, `reflections`
    - `voice_notices` (`chat_id` primary key)
  - `def check_voice_limits(duration_s: int, file_size: int, *, max_s: int = 300, max_bytes: int = 10_000_000) -> str | None` returns the refusal text `Please keep voice notes under 5 minutes.` or `That file is too large.`, or `None`
  - `async def intake_voice(session, file_bytes: bytes, duration_s: int, voice_dir: Path) -> int`: saves `data/voice/in/<sha>.ogg` with mode `0o640`, creates a `voice_sessions` row, defers `analyse_voice` (queue `voice`), and returns the session id
  - Bot reply: `Got it, analysing (about a minute).` The privacy notice is sent once per chat.
  - `def check_voice_bytes(head: bytes) -> str | None`: `None` when the first bytes are `OggS`, otherwise the refusal text. The analysis job also runs `probe_media` (phase 2c) and refuses any format other than `ogg`.

- [ ] **Step 1: Write the failing tests**

```python
def test_voice_too_long_refused():
    assert check_voice_limits(301, 1000) == "Please keep voice notes under 5 minutes."
    assert check_voice_limits(60, 10_000_001) == "That file is too large."
    assert check_voice_limits(60, 1000) is None

def test_non_ogg_voice_refused():
    assert check_voice_bytes(b"MZ\x90\x00 fake exe") == "I can only analyse Telegram voice notes."
    assert check_voice_bytes(b"OggS\x00\x02 fake") is None

@pytest.mark.db
async def test_intake_saves_private_file_and_defers(session, tmp_path, fake_defer):
    sid = await intake_voice(session, b"OggS fake", 60, tmp_path)
    f = next((tmp_path / "in").iterdir())
    assert f.stat().st_mode & 0o777 == 0o640 and fake_defer.calls[0][0] == "analyse_voice" and sid > 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_intake.py -v && uv run pytest -m db tests/voice/test_intake.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the migration, intake and voice handler (size and duration checked from Telegram metadata before downloading)**

- [ ] **Step 4: Run the tests**

Run: `docker compose run --rm migrate &&` the Step 2 commands
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice src/techradar/db src/techradar/bot compose.yaml tests/voice && git commit -m "feat(voice): Telegram voice note intake with limits"
```

### Task 2: `voice-worker` service and transcription

**SEC:** SEC-06-style isolation (no internet), SEC-07, SEC-23

**Files:**
- Create: `src/techradar/voice/audio.py`, `src/techradar/voice/transcribe.py`, `infra/docker/Dockerfile.voice`, `infra/models/voice.yaml`
- Modify: `compose.yaml` (add `voice-worker`: networks `db`, `llm`, `tools`; GPU reservation; mounts `./data/voice`; secret `tr_app_password`; baseline hardening; command `procrastinate … worker --queues=voice --concurrency=1`), `infra/falco/expected_programs.yaml` (`voice-worker: [python, ffmpeg]`; rerun the generator)
- Test: `tests/voice/test_audio.py`, `tests/voice/test_transcribe.py`

**Interfaces:**
- Produces:
  - `def decode_audio(path: Path, *, sr: int = 16_000, timeout_s: int = 60) -> np.ndarray`: runs `ffmpeg -nostdin -i <path> -ac 1 -ar 16000 -f f32le -` through `subprocess.run([...], capture_output=True, timeout=…)`
  - `def compute_peaks(wav: np.ndarray, n: int = 800) -> list[float]`: max absolute value per bucket, rounded to 3 decimals
  - `class Word(BaseModel)`: `text: str`, `start: float`, `end: float`, `prob: float`
  - `class Transcript(BaseModel)`: `text: str`, `words: list[Word]`, `lang: str`, `duration_s: float`
  - `FILLER_PROMPT = "Umm, let me think like, hmm... Okay, here's what I'm, like, thinking."`
  - `class Transcriber(Protocol)`: `def transcribe(self, path: Path) -> Transcript`
  - `class FasterWhisperTranscriber(Transcriber)`, built with `__init__(self, model_dir: Path, device: str = "cuda", compute_type: str = "int8_float16")`: `word_timestamps=True`, `vad_filter=True`, `initial_prompt=FILLER_PROMPT`, `condition_on_previous_text=False`
  - `def no_speech(t: Transcript) -> bool`: true if fewer than 3 words or the duration is under 1 s
  - **`infra/models/voice.yaml`:** for each voice model, `stt`, `stt_fallback` (`large-v3`), `phoneme`, `tts`: `{repo, revision, files}`
  - **`Dockerfile.voice`:**
    - Base: a CUDA runtime + cuDNN image, exact tag.
    - Python 3.14 via `uv python install`; ffmpeg and espeak-ng from apt.
    - Downloads the pinned models into `/opt/models/` at build time.
    - Runs `scripts/check_model_files.py`; the build fails on forbidden extensions.

- [ ] **Step 1: Write the failing tests**

```python
def test_compute_peaks_length_and_range():
    p = compute_peaks(np.sin(np.linspace(0, 100, 16_000)).astype("float32"), n=100)
    assert len(p) == 100 and all(0 <= v <= 1 for v in p)

def test_decode_audio_uses_list_args(monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: seen.setdefault("a", (args, kw)) or FakeCompleted(b"\x00" * 8))
    decode_audio(Path("x.ogg")); args, kw = seen["a"]
    assert isinstance(args, list) and "shell" not in kw and kw["timeout"] == 60

def test_silence_gives_no_speech():
    assert no_speech(Transcript(text="", words=[], lang="en", duration_s=5.0))

@pytest.mark.live
def test_transcribe_fixture_keeps_words(): ...   # a 10 s generated clip → ≥ 5 words with increasing timestamps
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_audio.py tests/voice/test_transcribe.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules, Dockerfile, model manifest and service**

- [ ] **Step 4: Run the tests, then build and try it on the server**

Run: `uv run pytest tests/voice -q && docker compose build voice-worker && docker compose run --rm voice-worker pytest -m live tests/voice/test_transcribe.py && uv run pytest tests/security/test_compose_policy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice infra/docker/Dockerfile.voice infra/models/voice.yaml compose.yaml tests/voice && git commit -m "feat(voice): voice-worker with faster-whisper transcription"
```

### Task 2b: Library audio transcription

**SEC:** SEC-07, SEC-15, SEC-23 (D38)

**Files:**
- Create: `src/techradar/voice/library_audio.py`
- Modify: `src/techradar/worker/tasks.py` (add `index_chapter_job`, queue `io`), `compose.yaml` (`voice-worker` mounts `./data/library/media` read-write and `./data/library/text` read-write)
- Test: `tests/voice/test_library_audio.py` (some tests marked `db`)

**Interfaces:**
- Consumes: `FasterWhisperTranscriber`, `Transcript`, `Word` (Task 2); `library_parts`, `library_chapters` (phase 2c); `index_library_chapter`, `render_ready`, `summarize_chapters_job` (phase 2c).
- Produces:
  - `def offset_words(words: Sequence[Word], offset_s: float) -> list[Word]`: adds the part's start time
  - `class TimedChapter(BaseModel)`: `ordinal: int`, `title: str`, `ts_start: float`, `ts_end: float`, `text: str`
  - `def chapters_by_time(words: Sequence[Word], slides: Sequence[SlideText], every_s: int = 900) -> list[TimedChapter]`:
    - **Titles:** `Part <n> (<mm:ss>–<mm:ss>)`.
    - **Text:** the spoken words, with each slide's text inserted at its time as a line `> Slide: <text>`.
    - **Time markers:** each line starts at a `<!-- t <seconds> -->` marker, so chunks get `ts_start`.
  - `transcribe_library_audio(doc_id: int)` job (queue `voice`, `night_only`, after `free_gpu`):
    1. Transcribes every pending audio part, marking each `done`.
    2. Builds the chapters and writes them to `data/library/text/<doc_id>/<NN>.md`.
    3. Creates the `library_chapters` rows and defers `index_chapter_job(chapter_id)` for each.
    4. Deletes the audio parts.
    5. Sets the doc to `ready`, sends `render_ready`, and queues the summaries.
  - **Picking up waiting videos:** `voice_idle_check` (every 30 minutes, queue `io`) defers `transcribe_library_audio` for every doc in `awaiting_transcription` when no voice note is waiting.
  - **Chunker:** `page_of` (phase 2c Task 6) also reads `<!-- t N -->` markers into `ts_start`.

- [ ] **Step 1: Write the failing tests**

```python
def test_offset_words():
    assert offset_words([Word(text="a", start=1.0, end=1.5, prob=0.9)], 600)[0].start == 601.0

def test_chapters_by_time_titles_and_slides():
    chs = chapters_by_time(words_over(1800), [SlideText(ts_s=30, text="Deadlocks")])
    assert [c.title for c in chs] == ["Part 1 (00:00–15:00)", "Part 2 (15:00–30:00)"] and "> Slide: Deadlocks" in chs[0].text

@pytest.mark.db
async def test_video_becomes_ready_after_transcription(session, awaiting_video, fake_transcriber, outbox):
    await transcribe_library_audio(awaiting_video.id, deps=deps_with(fake_transcriber))
    assert await doc_status(session, awaiting_video.id) == "ready" and outbox.texts[-1].startswith("Ready: ")
    assert not any((MEDIA / str(awaiting_video.id)).glob("*.flac"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_library_audio.py -v && uv run pytest -m db tests/voice/test_library_audio.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, the jobs and the mounts**

- [ ] **Step 4: Run the tests, then try a real video (owner)**

Run: same as Step 2. Then, on the server, wait for the next night window after dropping a 10-minute lecture into the Library folder.
Expected: PASS; the next morning, the Ready message arrives and answers cite times like `(12:40)`.

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice src/techradar/worker src/techradar/rag compose.yaml tests && git commit -m "feat(voice): transcribe library videos into timed chapters"
```

### Task 3: Speech metrics in code

**Files:**
- Create: `src/techradar/voice/metrics.py`
- Test: `tests/voice/test_metrics.py`

**Interfaces:**
- Produces:
  - `FILLERS = ("um", "uh", "er", "ah", "hmm", "basically", "actually", "you know", "i mean")`, plus `like` counted only when the next word starts 0.3 s or more after it ends, or when the transcript text has `like,`
  - `STOPWORDS`: a fixed set of the 100 most common English words, in the module
  - `class SpeechMetrics(BaseModel)`: `words_per_min: float`, `filler_count: int`, `fillers_per_min: float`, `filler_breakdown: dict[str, int]`, `long_pauses: int`, `avg_sentence_words: float`, `type_token_ratio: float`, `overused: list[tuple[str, int]]`
  - `def compute_metrics(t: Transcript) -> SpeechMetrics`:
    - Words per minute exclude fillers; rounded to 1 decimal.
    - A long pause is a gap between words of more than 1.0 s.
    - Type-token ratio uses words without fillers, lowercased; rounded to 2 decimals.
    - Overused words are non-stopwords used 5 or more times, top 3.

- [ ] **Step 1: Write the failing tests**

```python
def test_filler_counts_and_rate():
    m = compute_metrics(transcript_from("um so I think uh the rate um stayed", duration_s=60))
    assert m.filler_breakdown == {"um": 2, "uh": 1} and m.fillers_per_min == 3.0

def test_like_only_counted_as_filler_before_pause():
    assert compute_metrics(transcript_with_timings([("I", 0, .2), ("like", .2, .4), ("it", .5, .6)])).filler_count == 0
    assert compute_metrics(transcript_with_timings([("like", 0, .2), ("the", .6, .7)])).filler_count == 1

def test_long_pauses_and_ttr():
    m = compute_metrics(transcript_with_timings([("a", 0, .2), ("b", 1.5, 1.7), ("a", 1.8, 2.0)]))
    assert m.long_pauses == 1 and m.type_token_ratio == pytest.approx(0.67, abs=0.01)

def test_overused_words(): ...   # "very" ×6 → [("very", 6)]
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_metrics.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `metrics.py`**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice/metrics.py tests/voice/test_metrics.py && git commit -m "feat(voice): speech metrics computed in code"
```

### Task 4: LanguageTool grammar checks

**SEC:** SEC-07, SEC-17

**Files:**
- Create: `src/techradar/english/__init__.py`, `src/techradar/english/grammar_check.py`
- Modify: `compose.yaml` (add `languagetool`: image `<pinned LanguageTool server image>`, network `tools` only, no published port, baseline hardening, `mem_limit: 1g`), `infra/falco/expected_programs.yaml` (`languagetool: [java]`; rerun the generator)
- Test: `tests/english/test_grammar_check.py`, `tests/security/test_egress.py` (add a test)

**Interfaces:**
- Produces:
  - `class GrammarIssue(BaseModel)`: `rule_id: str`, `message: str` (≤300), `offset: int`, `length: int`, `replacements: list[str]` (≤3), `category: str`, `rule: GrammarRule | None`
  - `RULE_MAP: dict[str, GrammarRule]`: maps LanguageTool rule-ID prefixes to our rules, for example `EN_A_VS_AN` → `ARTICLES`, `HE_VERB_AGR` → `SUBJECT_VERB`, `PRP_` → `PRONOUNS`; an unknown ID gives `None`
  - `async def check_grammar(client: httpx.AsyncClient, base_url: str, text: str, language: str = "en-GB") -> list[GrammarIssue]`: `POST /v2/check` (form fields `text` and `language`), text capped at 5,000 characters
  - `def top_rule(issues: Sequence[GrammarIssue]) -> GrammarRule | None`: the most frequent mapped rule

- [ ] **Step 1: Write the failing tests**

```python
async def test_check_grammar_parses_fixture(respx_mock):
    respx_mock.post(f"{BASE}/v2/check").respond(json=LT_FIXTURE)
    issues = await check_grammar(client, BASE, "I has a apple")
    assert {i.rule for i in issues} == {GrammarRule.ARTICLES, GrammarRule.SUBJECT_VERB}

def test_text_capped():
    ...  # 6,000-char input → request body text length 5,000

@pytest.mark.egress
def test_languagetool_has_no_internet(): ...   # docker compose exec languagetool wget -T 5 https://example.com → non-zero
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/english -v`
Expected: FAIL

- [ ] **Step 3: Implement the client and the Compose service**

- [ ] **Step 4: Run the tests, the egress test and the policy check on the server**

Run: `uv run pytest tests/english && docker compose up -d languagetool && uv run pytest -m egress tests/security -q && uv run pytest tests/security/test_compose_policy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/english compose.yaml infra/falco tests && git commit -m "feat(english): offline LanguageTool grammar checks"
```

### Task 5: Pronunciation scoring with phonemes

**SEC:** SEC-23

**Files:**
- Create: `src/techradar/voice/phonemes.py`, `src/techradar/voice/align.py`, `src/techradar/voice/pronounce.py`
- Test: `tests/voice/test_align.py`, `tests/voice/test_pronounce.py`

**Interfaces:**
- Produces:
  - `FRAME_S = 0.02` (wav2vec2: 50 frames per second)
  - `FLAG_THRESHOLD = 0.5` (calibrated in Task 10)
  - `def expected_ipa(word: str, voice: str = "en-gb") -> str`: phonemizer with the espeak backend, `strip=True`, `with_stress=False`
  - `def to_vocab_ids(ipa: str, vocab: Mapping[str, int]) -> list[int]`: greedy longest match against vocab keys, skipping characters that aren't in the vocab
  - `def ctc_force_align(log_probs: np.ndarray, targets: Sequence[int], blank: int) -> list[tuple[int, int, int]]`: standard CTC Viterbi forced alignment over a `(frames, vocab)` log-probability matrix. Returns `(target_index, start_frame, end_frame)` for each target. Raises `ValueError` if there are fewer frames than the minimum the targets need.
  - `def phone_scores(log_probs: np.ndarray, alignment, targets) -> list[float]`: mean of `exp(log_prob[target])` over each target's frames
  - `class PhonemeModel(Protocol)`: `vocab: Mapping[str, int]`, `blank_id: int`, `def log_probs(self, wav: np.ndarray) -> np.ndarray`
  - `class Wav2Vec2PhonemeModel(PhonemeModel)`, built with `__init__(self, model_dir: Path, device: str)`: fp16 on CUDA, `trust_remote_code=False`
  - `class WordScore(BaseModel)`: `word`, `start_s`, `end_s`, `score: float`, `flagged: bool`
  - `def score_words(wav: np.ndarray, words: Sequence[Word], model: PhonemeModel) -> list[WordScore]`: aligns each word inside its own Whisper time window, padded by ±0.1 s, so errors can't drift across words. Skips words of 2 letters or fewer.

- [ ] **Step 1: Write the failing tests**

```python
def test_ctc_force_align_toy():
    lp = np.log(np.array([[.9, .1, 0, 0], [.1, .9, 0, 0], [.9, 0, .1, 0], [.1, 0, .9, 0]]) + 1e-9)
    assert ctc_force_align(lp, [1, 2], blank=0) == [(0, 1, 1), (1, 3, 3)]

def test_ctc_force_align_too_few_frames():
    with pytest.raises(ValueError): ctc_force_align(np.zeros((1, 3)), [1, 2], blank=0)

def test_to_vocab_ids_longest_match():
    assert to_vocab_ids("tʃa", {"t": 1, "tʃ": 2, "a": 3}) == [2, 3]

def test_score_words_flags_low_scores():
    ws = score_words(np.zeros(32_000, "float32"), [Word(text="world", start=0.2, end=0.8, prob=1)], FakePhonemeModel(prob=0.3))
    assert ws[0].flagged and ws[0].score == pytest.approx(0.3, abs=0.05)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_align.py tests/voice/test_pronounce.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules (`FakePhonemeModel` in `tests/fakes.py`)**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice tests && git commit -m "feat(voice): phoneme scoring with CTC forced alignment"
```

### Task 6: Fixes, spoken feedback, the analysis job and retention

**SEC:** SEC-15, SEC-17, SEC-18

**Files:**
- Create: `src/techradar/voice/feedback.py`, `src/techradar/voice/speak.py`, `src/techradar/voice/jobs.py`
- Modify: `src/techradar/bot/callbacks.py` (add `keep_voice`), `src/techradar/messaging/outbox.py` (send `voice` kind), `compose.yaml` (the `bot` mounts `./data/voice/out` read-only)
- Test: `tests/voice/test_feedback.py`, `tests/voice/test_jobs.py` (marker `db`)

**Interfaces:**
- Consumes: Tasks 2–5; `complete_json`; `enqueue_message`; `free_gpu` (phase 2c, `techradar.ops.gpu`).
- Produces:
  - `class Fix(BaseModel)`: `kind: Literal["grammar","pronunciation","filler","pace","vocabulary"]`, `detail: str` (≤200), `example: str` (≤200)
  - `def choose_fixes(m: SpeechMetrics, issues: Sequence[GrammarIssue], words: Sequence[WordScore]) -> list[Fix]`: up to 3, in priority order:
    1. the most frequent grammar rule
    2. the lowest-scoring flagged word
    3. fillers, if `fillers_per_min` is over 2.0
    4. pace, if under 100 or over 170 words per minute
    5. an overused word
  - `class VoiceFeedback(BaseModel)`: `summary: NoLinks` (≤400), `drill: NoLinks` (≤200)
  - `async def phrase_feedback(completer, fixes: Sequence[Fix], m: SpeechMetrics) -> VoiceFeedback`: the worker model, with inputs wrapped as untrusted
  - `def render_voice_report(duration_s: float, m: SpeechMetrics, issues, words, fixes, fb: VoiceFeedback) -> str`, exact lines:
    - `🎙️ Voice note · <m> min`
    - `Fluency: <wpm> words/min · <n> fillers (<rate>/min)`
    - `Grammar: <k> issues · <top rules>`
    - `Pronunciation: <up to 3 flagged words with scores>`
    - `Vocabulary: <overused or "good variety">`
    - `Top fixes: <fix 1> · <fix 2> · <fix 3>`
    - `Next drill: <drill>`
  - `class Speaker(Protocol)`: `def speak(self, text: str, out_path: Path) -> Path`
  - `class KokoroOnnxSpeaker(Speaker)`: voice `af_heart`; produces WAV, then OGG/Opus through ffmpeg
  - `analyse_voice(session_id: int)` job (queue `voice`):
    1. `free_gpu`
    2. decode
    3. transcribe; no speech gives the reply `I couldn't hear speech in that note.`
    4. metrics
    5. grammar
    6. phonemes
    7. fixes
    8. feedback
    9. speak a summary of up to 30 s
    10. store everything, plus peaks
    11. enqueue the text report with the button `Keep recording` (`keep_voice:<id>`), then the voice reply
    12. set `delete_after = now + 24h`
  - `cleanup_voice_job` (hourly): deletes input audio and generated replies past `delete_after` unless `kept`, and nulls `audio_path`

- [ ] **Step 1: Write the failing tests**

```python
def test_choose_fixes_priority_and_cap():
    fixes = choose_fixes(metrics(fillers_per_min=3.0, wpm=180, overused=[("very", 6)]), [ISSUE_ARTICLES] * 3, [WORD_WORLD_0_3])
    assert [f.kind for f in fixes] == ["grammar", "pronunciation", "filler"]

def test_render_voice_report_lines(): ...   # exact first two lines for a fixture

@pytest.mark.db
async def test_voice_job_frees_gpu_first(job_deps):
    await analyse_voice(job_deps.session_id)
    assert job_deps.calls[0] == "free_gpu"

@pytest.mark.db
async def test_no_speech_reply(job_deps_silent):
    await analyse_voice(job_deps_silent.session_id)
    assert job_deps_silent.outbox_texts == ["I couldn't hear speech in that note."]

@pytest.mark.db
async def test_audio_deleted_after_24h_unless_kept(job_deps):
    await analyse_voice(job_deps.session_id); await cleanup_voice(job_deps, now=NOW + timedelta(hours=25))
    assert not any((job_deps.voice_dir / "in").iterdir())
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_feedback.py -v && uv run pytest -m db tests/voice/test_jobs.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules, jobs, keep callback and voice outbox kind**

- [ ] **Step 4: Run the tests, then try a real voice note on the server**

Run: same as Step 2, then `docker compose up -d --build voice-worker bot` and send a 1-minute voice note.
Expected: tests pass; a text report and a short spoken summary arrive within about 2 minutes.

- [ ] **Step 5: Commit**

```bash
git add src/techradar/voice src/techradar/bot src/techradar/messaging compose.yaml tests/voice && git commit -m "feat(voice): analysis job, top-3 fixes, spoken summary, 24h audio retention"
```

### Task 7: Writing practice (take feedback, weekly essay or letter, `/polish`)

**SEC:** SEC-17, SEC-18, SEC-26

**Files:**
- Create: `src/techradar/english/writing.py`
- Modify:
  - `src/techradar/briefing/takes.py`: send feedback after saving, when `take_feedback` is on
  - `src/techradar/bot/routing.py`: add `polish`, and replies with purpose `essay`
  - `src/techradar/worker/tasks.py`: add `essay_prompt_job`, Saturdays at 10:00
- Test: `tests/english/test_writing.py`

**Interfaces:**
- Produces:
  - `class Rubric(BaseModel)`: `structure`, `grammar`, `vocabulary`, `relevance` (each 1–5)
  - `class WritingFeedback(BaseModel)`: `issues: list[GrammarIssue]`, `improved: NoLinks` (≤2000), `reasons: list[NoLinks]` (≤5), `rubric: Rubric | None`
  - `async def feedback_on_text(text: str, kind: Literal["take","essay","letter","polish"], lt, completer) -> WritingFeedback`: LanguageTool issues come first; the worker model writes `improved`, `reasons`, and for essays and letters, the rubric
  - `MAX_POLISH_CHARS = 2000`; over that, the reply is `Keep it under 2,000 characters.`
  - **Essay prompts:** topics from `practice/essay_topics.md` in the vault. Essays and letters alternate each week. A reply within 30 minutes counts as timed; later replies are marked `untimed`.
  - `def render_writing_feedback(fb: WritingFeedback) -> str`: `Improved:\n<improved>\n\nWhy:\n• …` plus a rubric line `Structure 4 · Grammar 3 · Vocabulary 4 · Relevance 5` when present

- [ ] **Step 1: Write the failing tests**

```python
async def test_essay_feedback_has_rubric(lt_fake):
    fb = await feedback_on_text("Dear Sir, ...", "letter", lt_fake, FakeCompleter([FEEDBACK_WITH_RUBRIC]))
    assert fb.rubric and 1 <= fb.rubric.structure <= 5

def test_polish_too_long():
    assert route_and_validate_polish("x" * 2001) == "Keep it under 2,000 characters."

def test_render_writing_feedback(): ...   # exact text for a fixture
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/english/test_writing.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, routing and job**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/english src/techradar/briefing src/techradar/bot src/techradar/worker tests/english && git commit -m "feat(english): writing feedback, weekly essay or letter, /polish"
```

### Task 8: Story bank, reading quiz, listening check and weekly reflection

**SEC:** SEC-15, SEC-18, SEC-24, SEC-26

**Files:**
- Create: `src/techradar/english/stories.py`, `src/techradar/english/reading.py`, `src/techradar/english/listening.py`, `src/techradar/english/reflection.py`
- Modify: `src/techradar/bot/routing.py` (add `story` and audio-with-caption `listen`), `src/techradar/worker/tasks.py` (add `reading_quiz_job` (Fridays 18:00) and `reflection_prompt_job` (Sundays 20:00))
- Test: `tests/english/test_stories.py`, `tests/english/test_reading.py`, `tests/english/test_listening.py`

**Interfaces:**
- Produces:
  - **Story bank:** `STAR_FIELDS = ("situation", "task", "action", "result")`; `async def story_step(session, chat_id: int, text: str | None) -> str` is a state machine over `story_drafts`. `/story` starts it, each reply fills the next field (up to 600 characters), and at the end it writes `stories` plus `stories/<slug>.md`. Replies:
    - `Situation? (what was happening)`
    - `Task? (what you had to do)`
    - `Action? (what you did)`
    - `Result? (what happened, with a number if you can)`
    - `Saved your story: <title>.`
  - **Reading quiz:** `async def reading_quiz(note_text: str, completer) -> list[MCQDraft]`, 5 questions. The correct option must appear word for word in the note text (whitespace-normalised), and the checker must agree; failing questions are dropped.
  - **Listening check:**
    - An owner audio file with the caption `listen` (up to 600 s and 20 MB) is transcribed by `voice-worker`. The bot then asks `Send a 3-line summary.`
    - `class KeyPoints(BaseModel)`: `points: list[NoLinks]` (3–6), extracted by the worker model
    - `class Coverage(BaseModel)`: `covered: list[int]`, judged by the checker from my summary
    - The reply is `You covered <c> of <t> key points. Missed: <up to 3>.` The audio follows the 24 h retention rule.
  - **Weekly reflection:** the prompt is `One conversation this week: what went well, and what would you do differently?` My reply (purpose `reflection`) is saved to `reflections/<YYYY>-W<ww>.md`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
async def test_story_state_machine(session):
    assert await story_step(session, 42, None) == "Situation? (what was happening)"
    for t in ["S", "T", "A"]: await story_step(session, 42, t)
    assert (await story_step(session, 42, "Cut load time by 40%")).startswith("Saved your story")

async def test_reading_quiz_drops_non_verbatim_answers():
    qs = await reading_quiz(NOTE, FakeCompleter([MCQ_VERBATIM, '{"answer_index": 0}', MCQ_INVENTED, '{"answer_index": 0}']))
    assert len(qs) == 1

async def test_listening_coverage_reply():
    assert render_coverage(KeyPoints(points=["a", "b", "c", "d"]), Coverage(covered=[0, 2])) == "You covered 2 of 4 key points. Missed: b, d."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/english -v && uv run pytest -m db tests/english -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules, routing and jobs**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/english src/techradar/bot src/techradar/worker tests/english && git commit -m "feat(english): story bank, reading quiz, listening check, reflection"
```

### Task 9: Voice report screen

**SEC:** SEC-15, SEC-27, SEC-28

**Files:**
- Create: `src/techradar/api/routes/voice.py`, `apps/web/src/app/(app)/voice/page.tsx`, `apps/web/src/app/(app)/voice/[id]/page.tsx`, `apps/web/src/components/voice/{SessionList,MetricCards,TrendCharts,WaveformPeaks,WordChips,FixList}.tsx`, `apps/web/tests/voice-report.spec.ts`
- Modify: `src/techradar/voice/jobs.py` (cache the correct pronunciation of flagged words as `data/voice/words/<slug>.ogg`), `tests/web_mock.py`
- Test: `apps/web/tests/voice-report.spec.ts`, `tests/api/test_voice_routes.py`

**Interfaces:**
- Produces:
  - **Routes:**
    - `GET /v1/voice/sessions`
    - `GET /v1/voice/sessions/{id}` returns `VoiceReport(metrics, fixes, words: list[WordScore], peaks, duration_s, kept, has_audio)`
    - `POST /v1/voice/sessions/{id}/keep`
    - `GET /v1/voice/sessions/{id}/audio` (404 unless kept)
    - `GET /v1/voice/words/{slug}` (cached correct pronunciation)
  - **`WaveformPeaks`:** wavesurfer.js with `peaks` and `duration`; regions for fillers (amber) and flagged words (red). Playback only when `has_audio`.
  - **`WordChips`:** coloured by score (green ≥ 0.75, amber ≥ 0.5, red < 0.5), each with an `aria-label` like `world, score 0.31`. Tapping plays the cached correct version.
  - **`TrendCharts`:** fillers per minute, words per minute and average pronunciation score over sessions.

- [ ] **Step 1: Write the failing tests**

```ts
test("report shows metrics and chips", async ({ page }) => {
  await page.goto("/voice/1"); await expect(page.getByText("132 words/min")).toBeVisible();
  await expect(page.getByLabel("world, score 0.31")).toBeVisible();
});
test("no audio element when not kept", async ({ page }) => {
  await page.goto("/voice/1"); expect(await page.locator("audio").count()).toBe(0);
});
```

```python
@pytest.mark.db
def test_audio_404_unless_kept(client): assert client.get("/v1/voice/sessions/1/audio", headers=AUTH).status_code == 404
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_voice_routes.py -v && cd apps/web && pnpm playwright test tests/voice-report.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the routes and screen**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar apps/web tests && git commit -m "feat(web): voice session report with peaks, word scores and trends"
```

### Task 9b: English practice time

**SEC:** SEC-26

**Files:**
- Modify: `src/techradar/api/routes/settings.py` (`UserSettings` gains `english_practice_time: str | None`), `src/techradar/worker/tasks.py` (`english_reminder_job`, every 15 minutes), `src/techradar/planner/plan.py` (a plan line for the practice time)
- Test: `tests/voice/test_practice_time.py`

**Interfaces:**
- Produces:
  - `english_practice_time` in `user_settings`: `HH:MM`, or null for no reminder (the default)
  - `ENGLISH_REMINDER`, exactly: `🎙️ English practice time. Send a voice note, or open Jarvis and say "Coach my English".`
  - `def reminder_due(now_local: datetime, at: time | None, last_sent: date | None) -> bool`: true at or after `at` on a day it hasn't been sent, until `at` plus 2 hours
  - **Plan line:** `🎙️ English practice at <HH:MM>`
  - **Coaching stays on demand (06 C2):** only voice notes I send, or sessions I start, are analysed. Nothing else I say is analysed.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("hhmm,last,due", [("18:59", None, False), ("19:00", None, True), ("21:01", None, False), ("19:30", "today", False)])
def test_reminder_due(hhmm, last, due):
    assert reminder_due(at_local(hhmm), time(19), TODAY if last else None) is due

def test_no_time_means_no_reminder():
    assert reminder_due(at_local("19:00"), None, None) is False
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/voice/test_practice_time.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the setting, the job and the plan line**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar tests && git commit -m "feat(voice): optional English practice time with a reminder"
```

### Task 10: Voice evals and gate 6

**SEC:** SEC-15, SEC-23, re-check of earlier controls

**Files:**
- Create: `evals/voice/clips.example.yaml`, `evals/voice/run.py`, `scripts/check_model_files.py`, `tests/scripts/test_check_model_files.py`
- Modify: `Makefile` (add `voice-eval` and `gate-6`)

**Interfaces:**
- Produces:
  - **Clip list:** `evals/voice/clips.yaml` (git-ignored) has entries `{path, hand_transcript, fillers: {um: n, …}, kind: free|read_correct|read_error}` for my 10 clips, plus 20 read sentences.
  - **`run.py`:**
    1. Computes filler recall (Whisper fillers matched to hand counts) for `large-v3-turbo`; if it's below 0.90, also for `large-v3`.
    2. Computes the phoneme flag rate on `read_correct` clips and the catch rate on `read_error` clips.
    3. Suggests a `FLAG_THRESHOLD` that keeps the flag rate at or under 10%.
    4. Writes `evals/voice/results/<date>.json`.
    5. Fails if filler recall is under 0.90 for both models, or if no threshold reaches a 10% flag rate with a catch rate of 60% or more.
  - **`check_model_files.py <dir>`:** exits 1 if any `.pt`, `.pth`, `.pkl` or `.ckpt` file exists. `.bin` is allowed only inside CTranslate2 model directories (those containing `model.bin` and `config.json`) and the wav2vec2 directory when torch ≥ 2.6.
  - **`make gate-6`:**
    1. `gate-5`
    2. `pytest tests/voice tests/english` (and `-m db`)
    3. Playwright `voice-report.spec.ts`
    4. `voice-eval`
    5. `check_model_files.py` inside the `voice-worker` image
    6. `pytest -m egress tests/security`
    7. The policy test
    8. Print the signing reminder.

- [ ] **Step 1: Write the failing tests for the model-file checker**

```python
def test_rejects_pickle_files(tmp_path):
    (tmp_path / "m.pth").write_bytes(b"x"); assert run_checker(tmp_path) == 1

def test_allows_ct2_bin(tmp_path):
    d = tmp_path / "whisper"; d.mkdir(); (d / "model.bin").write_bytes(b"x"); (d / "config.json").write_text("{}")
    assert run_checker(tmp_path) == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/scripts/test_check_model_files.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the checker and the eval runner; record my clips (owner)**

- [ ] **Step 4: Run the gate on the server**

Run: `make gate-6`
Expected: every step passes. Set `FLAG_THRESHOLD` to the suggested value in a commit before signing.

- [ ] **Step 5: Commit and sign**

```bash
git add evals/voice scripts tests Makefile src/techradar/voice/pronounce.py docs/security/gates.md && git commit -m "security(voice): model-file check, voice evals, gate 6 passed"
```
