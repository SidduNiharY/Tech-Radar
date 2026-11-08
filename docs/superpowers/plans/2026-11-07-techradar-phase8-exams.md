# TechRadar Brain Phase 8: Exams Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exam preparation tools. It ends with `make gate-8`. It delivers:
- syllabus coverage, with the sources linked to each topic and "no source yet" (added 2026-11-08)
- official answer keys captured when released (added 2026-11-08)
- a GATE past-paper bank with official answer keys
- code-generated aptitude, reasoning and speed-maths drills (keys always right)
- typing practice
- a mock-test analyser with cutoff comparison
- topic weightage
- final 30 days mode
- the Exams screen

**Architecture:**
- **Questions with fixed answers.** Answers come from official keys or are computed by code; models only suggest topic tags, which I confirm.
- **Screenshots and PDFs.** These are read only inside the no-network parser sandbox. Any model-extracted number must appear word for word in the OCR text.
- **Personal data stays local.** Past papers and my scores live in `data/` (git-ignored) and are never redistributed.

**Tech Stack:** Docling + RapidOCR (sandbox), Python `random` with fixed seeds, `packaging`, FastAPI, Next.js (heatmap, timers, typing test).

**Spec:** [01](../../../01_Idea_and_Daily_Use.md) (Goal 2 GATE, Goal 3 government exams, extra features: mock analyser, topic weightage, speed maths, typing, final 30 days) · [05](../../../05_Architecture.md) SEC-06, SEC-18 · [overview](2026-11-07-techradar-00-overview.md) D13, D27, D39 · [06](../../../06_Improvements.md) G2–G6 · phase 5 `compose_plan(final_30_exam=…)` · phase 2c (library chapters, `trust_for`, packs) · phase 3 `final30_reviews`

## Global Constraints

- The overview's Global Constraints 1–16 apply.
- **Sandbox only:** images (`png`, `jpg`, `jpeg`, up to 5 MB) and PDFs are parsed only in the parser sandbox (SEC-06). `techradar.exams` must never import `docling` or `rapidocr`.
- **Code-generated drills (D27):** every item carries `meta` so tests can recompute the answer independently. Exactly 4 options, unique.
- **Daily set:** 10 quant and 10 reasoning questions per day, seeded by the date so Telegram and the web show the same set.
- **Answer keys:** the API never sends answer keys or `answer_index` before an answer is submitted.
- **Cutoffs:** the CSV `source_url` must be on an official domain. Weightage from post-exam analyses is labelled `analysis (unverified)`.
- **Topic sources:** a model-suggested source counts only after I confirm it; confirmed past-paper tags link automatically.
- **Answer keys:** only links matching a pattern anchored to an official host; links are found by code, never by a model.
- **Bank exams:** "memory-based" papers are labelled `memory-based (unverified)` wherever they appear (06 G6.2).

## Review Focus

1. **A blurry scorecard screenshot** must not produce invented numbers; it asks me to type the scores. Task 5 `test_numbers_must_appear_in_ocr`.
2. **A GATE numerical answer inside the accepted range** (for example 1.55 for "1.5 to 1.6") is marked correct. Task 2 `test_nat_range_inclusive`.
3. **Telegram and the web** show the same daily drill set. Task 4 `test_daily_set_is_deterministic`.
4. **No exam date set** means final 30 days mode stays off with no errors. Task 7 `test_final_30_none_without_dates`.
5. **Leaving the browser before the drill ends** keeps the answers already given. Task 8 `drill progress persists per answer`.

Also pinned on 2026-11-08:
- **A model linking a chapter to the wrong topic** changes nothing until I confirm it. Task 2b `test_suggested_source_needs_my_confirmation`.
- **An answer-key link to a site that isn't official** is never downloaded. Task 6b `test_matching_links_only_pattern_and_absolute`.

---

### Task 1: Syllabus topics and coverage

**Files:**
- Create: `src/techradar/exams/__init__.py`, `src/techradar/exams/syllabus.py`, `src/techradar/db/migrations/versions/0010_exams.py`
- Test: `tests/exams/test_syllabus.py`

**Interfaces:**
- Produces:
  - **Migration `0010_exams`:**
    - `syllabus_topics` (`id`, `exam`, `subject`, `topic`, `slug`, `vault_path`; unique on `exam`, `subject`, `slug`)
    - `pyq_questions` (`id`, `exam`, `year`, `paper`, `number`, `text`, `options` jsonb null, `qtype` (`MCQ`, `MSQ`, `NAT`), `answer_key` text, `marks` numeric, `topic_id` null, `tag_status` (`none`, `suggested`, `confirmed`))
    - `drill_attempts` (`id`, `day`, `kind`, `item` jsonb, `chosen` text, `correct` bool, `seconds` real, `at`)
    - `mock_results` (`id`, `exam`, `taken_on`, `total`, `max_total` null, `sections` jsonb, `source` text, `created_at`)
    - `cutoffs` (`exam`, `year`, `tier`, `category`, `score`, `source_url`)
    - `topic_weights` (`exam`, `subject`, `topic`, `weight`, `source`)
  - `def parse_topics(md: str) -> list[str]`: `- ` lines under `## Topics`, up to the next heading; each up to 120 characters
  - `async def sync_syllabus(session, vault_root: Path) -> int`: reads every `syllabus/**/*.md` (front matter `exam`, `title` as the subject)
  - `class TopicCoverage(BaseModel)`: `subject`, `topic`, `studied_minutes: int`, `revisions_done: int`, `covered: bool`
  - `async def coverage(session, exam: str) -> list[TopicCoverage]`: a topic is covered with at least 30 studied minutes or 1 completed revision. Topic names match `study_sessions.topic` case-insensitively.
  - `syllabus_sync_job`: queue `io`, daily

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_topics_stops_at_next_heading():
    md = "# OS\n## Topics\n- Processes\n- Deadlocks\n## Notes\n- not a topic\n"
    assert parse_topics(md) == ["Processes", "Deadlocks"]

@pytest.mark.db
async def test_coverage_rules(session): ...   # 45 min on "deadlocks" → covered; 10 min + 0 revisions → not covered
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_syllabus.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the migration, module and job**

- [ ] **Step 4: Run the tests**

Run: `docker compose run --rm migrate && uv run pytest tests/exams && uv run pytest -m db tests/exams -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/db tests/exams && git commit -m "feat(exams): syllabus topics and coverage"
```

### Task 2: GATE past-paper bank

**SEC:** SEC-06, SEC-18

**Files:**
- Create: `src/techradar/exams/pyq.py`
- Modify: `src/techradar/library/inbox.py` (phase 2c skips `library-inbox/gate/`; this task picks up `gate/<year>/` PDFs as `pyq` parse jobs through the Intake Gateway, instead of library documents)
- Test: `tests/exams/test_pyq.py`

**Interfaces:**
- Produces:
  - `class QuestionChunk(BaseModel)`: `number: int`, `text: str`, `options: list[str] | None`
  - `def split_questions(text: str) -> list[QuestionChunk]`: questions start at lines matching `^\s*Q\.?\s*(\d{1,2})\b`; options are lines starting `(A)`–`(D)`
  - `class KeyEntry(BaseModel)`: `qtype: Literal["MCQ","MSQ","NAT"]`, `key: str`, `marks: float`
  - `def parse_answer_key(text: str) -> dict[int, KeyEntry]`: one row per question with the number, type, key (`A`; `A;C`; or `1.5 to 1.6`) and marks
  - `def check_answer(e: KeyEntry, response: str) -> bool`:
    - MCQ: exact letter.
    - MSQ: the same set of letters.
    - NAT: a float within the inclusive range, or equal to the single value within ±1e-9.
  - `async def suggest_topic(completer, q: QuestionChunk, topics: Sequence[str]) -> str | None`: the worker model's suggestion must be in `topics`, and the checker must agree; otherwise `None`. Stored as `tag_status = 'suggested'`; only `confirmed` tags count later.
  - **File layout (owner):** official papers and keys go in `data/library-inbox/gate/<year>/<paper>-<year>.pdf` and `…-key.pdf`.

- [ ] **Step 1: Write the failing tests**

```python
def test_split_questions_fixture():
    qs = split_questions(GATE_TEXT_FIXTURE)
    assert [q.number for q in qs] == [1, 2, 3] and qs[0].options == ["(A) 2", "(B) 4", "(C) 8", "(D) 16"]

def test_parse_answer_key_rows():
    keys = parse_answer_key("1 MCQ GA A 1\n2 MSQ CS A;C 2\n3 NAT CS 1.5 to 1.6 2\n")
    assert keys[2].key == "A;C" and keys[3].qtype == "NAT"

def test_nat_range_inclusive():
    assert check_answer(KeyEntry(qtype="NAT", key="1.5 to 1.6", marks=2), "1.55")
    assert check_answer(KeyEntry(qtype="NAT", key="1.5 to 1.6", marks=2), "1.6")
    assert not check_answer(KeyEntry(qtype="NAT", key="1.5 to 1.6", marks=2), "1.61")

def test_msq_set_equality():
    assert check_answer(KeyEntry(qtype="MSQ", key="A;C", marks=2), "C;A") and not check_answer(KeyEntry(qtype="MSQ", key="A;C", marks=2), "A")

async def test_suggest_topic_must_be_in_list():
    assert await suggest_topic(FakeCompleter(['{"topic": "Cooking"}']), Q, ["Deadlocks", "Paging"]) is None
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_pyq.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `pyq.py` and the inbox routing**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/rag tests/exams && git commit -m "feat(exams): GATE past papers with official answer keys"
```

### Task 2b: Sources for every syllabus topic

**SEC:** SEC-18, SEC-20, SEC-26

**Files:**
- Create: `src/techradar/exams/sources.py`
- Modify: `src/techradar/bot/callbacks.py` (add `srcok`, `srcno`), `src/techradar/worker/tasks.py` (`suggest_topic_sources_job`, nightly, queue `llm`; `sources_digest_job`, Sundays at 18:15)
- Test: `tests/exams/test_sources.py` (some tests marked `db`)

**Interfaces:**
- Consumes: `syllabus_topics`, `pyq_questions` (Tasks 1–2); `library_chapters`, `chunks` (phase 2c); `Embedder`; `complete_json`, `Role.WORKER`, `Role.CHECKER`.
- Produces:
  - **`topic_sources` table** (added to `0010_exams`):
    - `id`, `topic_id` fk, `kind` (`chapter`, `pyq`, `pack_item`, `note`), `ref_id` bigint
    - `label` varchar(200), for example `Galvin · 8. Deadlocks · p. 318–352` or `GATE 2023 Q14`
    - `status` (`suggested`, `confirmed`, `dismissed`), `created_at`, `confirmed_at` null
    - unique on `(topic_id, kind, ref_id)`
  - `def candidate_topics(chapter_vec: Sequence[float], topic_vecs: Mapping[int, Sequence[float]], k: int = 3, min_cos: float = 0.55) -> list[int]`
  - `async def suggest_for_chapter(completer, chapter: ChapterRow, candidates: Sequence[TopicRow]) -> int | None`: the worker model picks one candidate topic ID (it must be in the list) and the checker must agree; otherwise `None`
  - `async def suggest_topic_sources(session, embedder, completer, *, max_per_night: int = 30) -> int`:
    - **Chapters:** for unlinked library chapters, the chapter vector is the embedding of its title plus its summary's key ideas; an agreed pick becomes a `suggested` source.
    - **Past papers:** PYQs whose topic tag is `confirmed` become `confirmed` sources at once, since I already confirmed them.
  - `async def decide_source(session, source_id: int, keep: bool, now: datetime) -> None`
  - **`coverage` (Task 1) adds** `n_sources: int` and `has_source: bool` (at least one confirmed source) to `TopicCoverage`
  - **Weekly digest:** `Sources to confirm: <n>`, then one message per suggestion, `<topic> ← <label>`, with buttons `Keep` (`srcok:<id>`) and `Not this` (`srcno:<id>`), at most 10 a week
  - `async def topics_without_sources(session, exam: str) -> list[TopicRow]`, which phase 12's suggestions use

- [ ] **Step 1: Write the failing tests**

```python
def test_candidate_topics_threshold():
    assert candidate_topics([1, 0], {1: [1, 0], 2: [0, 1]}, k=3, min_cos=0.55) == [1]

async def test_suggestion_must_be_in_candidates():
    assert await suggest_for_chapter(FakeCompleter(['{"topic_id": 999}']), CHAPTER, [TOPIC_DEADLOCKS]) is None

@pytest.mark.db
async def test_confirmed_pyq_tag_links_automatically(session, confirmed_pyq):
    await suggest_topic_sources(session, FakeEmbedder(), FakeCompleter([]))
    assert await source_status(session, confirmed_pyq.topic_id, "pyq") == "confirmed"

@pytest.mark.db
async def test_suggested_source_needs_my_confirmation(session, chapter_and_topic):
    await suggest_topic_sources(session, AGREEING_EMBEDDER, agreeing_completer(chapter_and_topic.topic_id))
    assert not (await coverage_for(session, chapter_and_topic.topic_id)).has_source
    await decide_source(session, await only_source_id(session), keep=True, now=NOW)
    assert (await coverage_for(session, chapter_and_topic.topic_id)).has_source
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_sources.py -v && uv run pytest -m db tests/exams/test_sources.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the table, module, callbacks and jobs**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/db src/techradar/bot src/techradar/worker tests && git commit -m "feat(exams): sources for every topic, suggested by models and confirmed by me"
```

### Task 3: Code-generated drills

**Files:**
- Create: `src/techradar/exams/drills/__init__.py`, `src/techradar/exams/drills/{quant,reasoning,speed,typing}.py`
- Test: `tests/exams/test_drills.py`

**Interfaces:**
- Produces:
  - `class DrillItem(BaseModel)`: `kind: str`, `question: str`, `options: list[str]` (exactly 4, unique), `answer_index: int`, `explanation: str`, `meta: dict[str, int | float | str]`
  - **Quant generators** (each `def gen_<name>(rng: random.Random) -> DrillItem`): `percentage_of`, `percent_change`, `ratio_share`, `simple_interest`, `compound_interest` (annual, 2 decimals), `profit_loss_percent`, `average`, `time_speed_distance`, `work_together`. Values are chosen so answers are whole numbers or have 2 decimals; distractors come from common mistakes (for example simple interest offered for a compound interest question).
  - **Reasoning generators:** `number_series` (arithmetic, geometric, squares, alternating), `coding_decoding` (letter shift), `direction_sense` (integer Pythagorean distances; final direction), `odd_one_out` (prime versus composite).
  - **Speed-maths generators:** `table` (2–30 × 2–12), `square` (1–50), `cube` (1–20), `percent_fraction` (common fractions such as 1/8 = 12.5%), `approximation` (two 2-digit numbers; options spaced at least 10% apart).
  - `def daily_set(day: date, n_quant: int = 10, n_reasoning: int = 10) -> list[DrillItem]`, seeded with `day.toordinal()`
  - **Typing:**
    - `def typing_passage(sentences: Sequence[str], rng, target_keys: int = 2000) -> str`: from my English notes, sanitised to printable ASCII
    - `def score_typing(passage: str, typed: str, seconds: float) -> TypingScore(key_depressions: int, accuracy: float, wpm: float)`: accuracy is `1 - edit_distance / len(passage)` (pure-Python dynamic programming, capped at 3,000 characters); words per minute counts 5 characters as one word

- [ ] **Step 1: Write the failing tests (200 seeds per generator, independent recomputation from `meta`)**

```python
@pytest.mark.parametrize("gen,recompute", GENERATORS_WITH_ORACLES)   # e.g. (gen_compound_interest, lambda m: round(m["p"]*(1+m["r"]/100)**m["t"]-m["p"], 2))
def test_generator_answers_are_correct(gen, recompute):
    for seed in range(200):
        item = gen(random.Random(seed))
        assert len(set(item.options)) == 4 and item.options[item.answer_index] == format_answer(recompute(item.meta))

def test_daily_set_same_for_same_day():
    assert daily_set(date(2026, 11, 8)) == daily_set(date(2026, 11, 8)) != daily_set(date(2026, 11, 9))

def test_score_typing():
    s = score_typing("hello world", "helo world", 6.0)
    assert s.accuracy == pytest.approx(1 - 1 / 11, abs=1e-3) and s.wpm == pytest.approx(20.0, abs=0.5)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_drills.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the generators**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS (200 seeds × every generator)

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams/drills tests/exams/test_drills.py && git commit -m "feat(exams): code-generated aptitude, reasoning, speed maths and typing"
```

### Task 4: Daily drills on Telegram

**SEC:** SEC-26

**Files:**
- Create: `src/techradar/exams/deliver.py`
- Modify: `src/techradar/bot/routing.py` (add `drill`), `src/techradar/bot/callbacks.py` (add `drill`)
- Test: `tests/exams/test_deliver.py`

**Interfaces:**
- Produces:
  - `/drill`: sends the day's 20 items one at a time, with buttons `drill:<n>:<0-3>` (`n` = index 0–19)
  - `async def record_drill(session, day: date, n: int, chosen: int, sent_at: datetime, now: datetime) -> DrillOutcome`: stores `drill_attempts` with `seconds = now - sent_at`; idempotent per `(day, n)`
  - `def render_drill_summary(attempts: Sequence[DrillAttempt]) -> str`: `Aptitude: <c>/<t> · avg <s> s per question · slowest: <kind>`

- [ ] **Step 1: Write the failing tests**

```python
def test_daily_set_is_deterministic(): assert [i.question for i in daily_set(D)] == [i.question for i in daily_set(D)]

@pytest.mark.db
async def test_record_drill_idempotent_and_timed(session): ...   # second tap ignored; seconds == 41.0

def test_render_drill_summary(): ...   # exact string for a fixture
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_deliver.py -v`
Expected: FAIL

- [ ] **Step 3: Implement delivery, routing and callbacks**

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/exams && uv run pytest -m db tests/exams -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/bot tests/exams && git commit -m "feat(exams): timed daily drills on Telegram"
```

### Task 5: Mock-test analyser

**SEC:** SEC-06, SEC-17, SEC-18

**Files:**
- Create: `src/techradar/exams/mocks.py`, `src/techradar/parser/image.py`
- Modify:
  - `src/techradar/schemas/pipeline.py`: `JobKind` adds `"image"`; `raw_name` allows `png`, `jpg` and `jpeg`; `purpose` adds `"mock"`
  - `src/techradar/parser/main.py`: dispatches images
  - `src/techradar/bot/intake.py`: an image or PDF with the caption `mock` becomes a `purpose="mock"` job
  - `src/techradar/settings.py`: `exam_category: str = "General"`
- Test: `tests/exams/test_mocks.py`, `tests/parser/test_image.py`

**Interfaces:**
- Produces:
  - `def image_to_doc(path: Path, url: str, max_chars: int, artifacts_path: Path) -> CleanDoc | None`: Docling image input with RapidOCR, inside the sandbox
  - `class SectionScore(BaseModel)`: `name` (≤40), `score: float`, `max_score: float | None`, `attempted: int | None`, `correct: int | None`, `time_min: float | None`
  - `class MockScore(BaseModel)`: `exam` (≤40), `total: float`, `max_total: float | None`, `sections: list[SectionScore]` (≤8)
  - `def extract_mock_regex(text: str) -> MockScore | None`: patterns `Total Score:? <x> ?/ ?<y>`, `<Section name> <x> ?/ ?<y>`, `Attempted:? <n>`, `Correct:? <n>`
  - `def numbers_present(score: MockScore, text: str) -> bool`: every number in the score must appear in the text (normalised: commas removed, `.0` optional)
  - `async def extract_mock(completer, text: str) -> MockScore | None`: regex first; otherwise the worker model (text wrapped as untrusted), accepted only if `numbers_present`
  - `def render_mock_reply(m: MockScore, cutoff: float | None, category: str) -> str`, exact lines:
    - `📊 Mock saved: <total>/<max>.`
    - `You're <gap> marks below|above last year's cutoff (<cutoff>, <category>).` (only when there's a cutoff)
    - `<Section> is where you can gain the most (<score>/<max>).` (the lowest ratio)
  - **When extraction fails:** `I couldn't read that scorecard reliably. Please type the scores: /mock <section>=<score>/<max> …`

- [ ] **Step 1: Write the failing tests**

```python
def test_extract_mock_regex_fixture():
    m = extract_mock_regex("Total Score: 123.5 / 200\nQuantitative Aptitude 32.5 / 50\nEnglish 41 / 50")
    assert m.total == 123.5 and m.sections[0].name == "Quantitative Aptitude"

def test_numbers_must_appear_in_ocr():
    assert not numbers_present(MockScore(exam="SSC", total=150.0, max_total=200.0, sections=[]), "Total Score: 123.5 / 200")

async def test_model_fallback_rejected_when_numbers_invented():
    assert await extract_mock(FakeCompleter(['{"exam":"SSC","total":150,"max_total":200,"sections":[]}']), "garbled 123.5 / 200") is None

def test_render_mock_reply_with_cutoff():
    assert render_mock_reply(MOCK, 136.0, "General").splitlines()[1] == "You're 12.5 marks below last year's cutoff (136.0, General)."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_mocks.py tests/parser/test_image.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the modules and the schema, parser and intake changes**

- [ ] **Step 4: Run the tests, sandbox test and contracts**

Add the contract: `techradar.exams` must not import `docling` or `rapidocr`.

Run: same as Step 2, then `uv run pytest -m egress tests/security/test_parser_sandbox.py && uv run lint-imports`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar pyproject.toml tests && git commit -m "feat(exams): sandboxed mock scorecard analyser with cutoff gap"
```

### Task 6: Cutoffs and topic weightage

**SEC:** SEC-18, SEC-20

**Files:**
- Create: `src/techradar/exams/weights.py`
- Test: `tests/exams/test_weights.py`

**Interfaces:**
- Produces:
  - **CSV imports (owner):**
    - `data/library-inbox/cutoffs/*.csv` with columns `exam,year,tier,category,score,source_url`
    - `data/library-inbox/weightage/*.csv` with columns `exam,subject,topic,questions,year,source_url`
  - `def import_cutoffs(rows: Iterable[dict], official: frozenset[str]) -> list[CutoffRow]`: rejects rows whose URL domain isn't official, or whose score is negative or non-numeric
  - `def import_weightage(rows) -> list[WeightRow]`: `source = "analysis"`
  - `def gate_weights(confirmed: Sequence[PyqRow]) -> list[TopicWeight(subject, topic, marks_total, share)]`: shares sum to 1.0

- [ ] **Step 1: Write the failing tests**

```python
def test_cutoff_requires_official_source():
    assert import_cutoffs([{"exam": "SSC CGL", "year": "2025", "tier": "1", "category": "General", "score": "136", "source_url": "https://blog.example/x"}], OFFICIAL) == []

def test_gate_weights_sum_to_one():
    assert sum(w.share for w in gate_weights(CONFIRMED_ROWS)) == pytest.approx(1.0)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_weights.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `weights.py` and the import job (queue `io`, watches the inbox folders)**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams tests/exams && git commit -m "feat(exams): official cutoffs and topic weightage"
```

### Task 6b: Official answer keys captured when released

**SEC:** SEC-05, SEC-25, SEC-57

**Files:**
- Create: `src/techradar/exams/answer_keys.py`
- Modify:
  - `src/techradar/db/migrations/versions/0010_exams.py`: `exam_watches` gains `capture_pattern` text null and `capture_exam` text null
  - `src/techradar/alerts/watcher.py`: phase 3's watcher job calls `capture_answer_keys` when a watch with a pattern changes
  - `compose.yaml`: the fetcher's `./data/library-packs` mount (phase 2c) is reused
- Test: `tests/exams/test_answer_keys.py` (some tests marked `db`)

**Interfaces:**
- Consumes: `fetch_url` (phase 2); `trust_for`, `plan_library_intake` (phase 2c); `exam_watches` (phase 3).
- Produces:
  - **`capture_pattern`:** a regular expression that I set, anchored to an official host, for example `^https://ssc\.gov\.in/.+answer.+\.pdf$`.
    - On load, a pattern is refused unless it starts with `^https://` followed by an allowlisted official host (by `trust_for`).
  - `def matching_links(html: str, base_url: str, pattern: re.Pattern) -> list[str]`:
    - absolute `href`s parsed with the standard library's `html.parser`, never a model
    - kept only when they match `pattern`
    - deduplicated, in page order
    - at most 20
  - `async def capture_answer_keys(deps, session, watch: WatchRow) -> int`:
    1. fetches the watched page through the fetcher's normal path
    2. downloads each matching PDF not yet seen (by URL) into `library-packs/answer_keys/<exam>/<YYYY>/`
    3. intake picks the files up as origin `pack`, trust `official`, `exam_tags=[<exam>]`
    4. returns the count
  - **Notice:** `New answer key saved: <file name> (<EXAM>). It's in your library.`

- [ ] **Step 1: Write the failing tests**

```python
def test_matching_links_only_pattern_and_absolute():
    html = '<a href="/res/ans_key_cgl.pdf">Key</a><a href="https://evil.example/answer.pdf">x</a>'
    assert matching_links(html, "https://ssc.gov.in/notices", re.compile(r"^https://ssc\.gov\.in/.+ans.+\.pdf$")) == ["https://ssc.gov.in/res/ans_key_cgl.pdf"]

def test_pattern_must_anchor_official_host():
    with pytest.raises(ValueError): load_capture_pattern(r"^https://free-pdfs\.example/.+\.pdf$")
    with pytest.raises(ValueError): load_capture_pattern(r".+answer.+\.pdf")

@pytest.mark.db
async def test_same_key_not_downloaded_twice(session, watch_with_pattern, respx_mock):
    await capture_answer_keys(DEPS, session, watch_with_pattern)
    assert await capture_answer_keys(DEPS, session, watch_with_pattern) == 0
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_answer_keys.py -v && uv run pytest -m db tests/exams/test_answer_keys.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, the columns and the watcher hook**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/alerts src/techradar/db tests && git commit -m "feat(exams): capture official answer keys when released"
```

### Task 7: Final 30 days mode

**SEC:** SEC-37, SEC-38

**Files:**
- Create: `src/techradar/exams/final30.py`
- Modify: `src/techradar/planner/plan.py` (in final mode, the goal line becomes `🎓 <GOAL>: revise <topic> (45 min)`, never "next topic"), `src/techradar/worker/tasks.py` (add the night `formula_sheets_job`)
- Test: `tests/exams/test_final30.py`

**Interfaces:**
- Produces:
  - `def final_30(exam_dates: Mapping[str, date], today: date) -> str | None`: the nearest exam 0–30 days away. While it's on, `due_cards` uses `final30_reviews` (80) instead of `daily_reviews` (phase 3, D39)
  - `def mini_mock(exam: str, day: date) -> list[DrillItem | PyqRef]`: 20 items, from PYQs for GATE and from drills for the government exams
  - `async def write_formula_sheet(exam: str, subject: str, deps: RagDeps, vault_root: Path) -> Literal["written","not_enough_sources","needs_review"]`: grounded and citation-checked; writes `final30/<exam>/<subject-slug>.md`
  - `def capsule_bundle(vault_root: Path, today: date) -> str`: writes `final30/current-affairs.md` linking the last 6 monthly capsules

- [ ] **Step 1: Write the failing tests**

```python
def test_final_30_none_without_dates(): assert final_30({}, date(2026, 11, 8)) is None
def test_final_30_picks_nearest_within_30():
    assert final_30({"SSC CGL": date(2026, 12, 1), "GATE": date(2027, 2, 1)}, date(2026, 11, 8)) == "SSC CGL"

def test_plan_in_final_mode_never_suggests_new_topic():
    assert not any("next topic" in l for l in compose_plan(TODAY, due_revisions=[], due_cards=0, quiz_ready=False,
               minutes_this_week={}, targets=TARGETS, priority=[Goal.GOV], final_30_exam="SSC CGL"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/exams/test_final30.py tests/planner -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, plan change and job**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/exams src/techradar/planner src/techradar/worker tests && git commit -m "feat(exams): final 30 days mode"
```

### Task 8: Exams screen

**SEC:** SEC-27, SEC-28

**Files:**
- Create: `src/techradar/api/routes/exams.py`, `apps/web/src/app/(app)/exams/page.tsx`, `apps/web/src/components/exams/{CoverageHeatmap,PyqPractice,DrillRunner,TypingTest,MockTable,WeightChart,Countdown}.tsx`, `apps/web/tests/exams.spec.ts`
- Modify: `tests/web_mock.py`
- Test: `apps/web/tests/exams.spec.ts`, `tests/api/test_exam_routes.py`

**Interfaces:**
- Produces:
  - **Routes** (all under `/v1/exams`):
    - `/coverage?exam=`
    - `/pyq/next?exam=&topic=` (no key), `/pyq/{id}/answer`
    - `/drills/today` (no keys), `/drills/{n}/answer`
    - `/typing/passage`, `/typing/score`
    - `/mocks`
    - `/weights?exam=`
    - `/countdown`
    - `/pyq/{id}/tag/confirm` (I confirm a suggested tag)
    - `/sources?exam=&status=suggested` and `/sources/{id}/decide` taking `{keep: bool}` (Task 2b)
  - **Screen tabs:** Coverage (subjects × topics grid, each cell with an `aria-label` like `Deadlocks, covered` or `Banker's algorithm, no source yet`), Sources (suggested sources with Keep and Not this), Past papers, Drills (timer; keys A–D; progress saved after every answer), Typing (live words per minute and accuracy at the end), Mocks (table and chart against the cutoff), Weightage (bars, with `analysis (unverified)` badges), Countdown.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
def test_drills_today_hides_keys(client): assert all("answer_index" not in d for d in client.get("/v1/exams/drills/today", headers=AUTH).json())
```

```ts
test("coverage cells are labelled", async ({ page }) => { await page.goto("/exams"); await expect(page.getByLabel("Deadlocks, covered")).toBeVisible(); });
test("topics without sources say so", async ({ page }) => { await page.goto("/exams"); await expect(page.getByLabel("Banker's algorithm, no source yet")).toBeVisible(); });
test("drill progress persists per answer", async ({ page }) => {
  await page.goto("/exams?tab=drills"); await page.keyboard.press("a"); await page.reload();
  await expect(page.getByText("Question 2 of 20")).toBeVisible();
});
test("typing test scores", async ({ page }) => { /* type the passage; accuracy and wpm shown */ });
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest -m db tests/api/test_exam_routes.py -v && cd apps/web && pnpm playwright test tests/exams.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the routes and screen**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/api apps/web tests && git commit -m "feat(web): Exams screen"
```

### Task 9: Gate 8

**Files:**
- Modify: `Makefile` (add `gate-8`), `docs/security/gates.md`

**Interfaces:**
- Produces: **`make gate-8`:**
  1. `gate-7`
  2. `pytest tests/exams tests/parser` (and `-m db`, `-m slow`), including the topic-source and answer-key tests
  3. The parser sandbox test
  4. `lint-imports`
  5. Playwright `exams.spec.ts`
  6. Print the signing reminder.

- [ ] **Step 1: Run the gate on the server**

Run: `make gate-8`
Expected: every step passes.

- [ ] **Step 2: Commit and sign**

```bash
git add Makefile docs/security/gates.md && git commit -m "docs(security): gate 8 passed"
```
