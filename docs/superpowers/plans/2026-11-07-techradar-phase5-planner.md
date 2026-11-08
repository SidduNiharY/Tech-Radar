# TechRadar Brain Phase 5: Planner, Progress and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily plan inside the briefing, a 1–7–30 revision calendar (with +90 for exam topics and for chapters I mark as read), a study time tracker, a one-tap energy check-in, a Progress screen with a weekly review, skill map updates, and failure and health alerts. It ends with `make gate-5`.

**Architecture:** Plain code (no AI) computes plans, revisions, streaks and patterns from Postgres. The bot records sessions and check-ins; the worker composes plan lines for the briefing and sends alerts through the outbox. Server jobs never fall back to the Mac (D19); when the server is off, jobs wait and catch up.

**Tech Stack:** Procrastinate, python-telegram-bot, FastAPI, Next.js + shadcn charts (Recharts).

**Spec:** [01](../../../01_Idea_and_Daily_Use.md) (build step 5, study time tracker, energy check-in, revision calendar, weekly review, skill map) · [05](../../../05_Architecture.md) §6 · [overview](2026-11-07-techradar-00-overview.md) D19, D23, D39 · [06](../../../06_Improvements.md) A6, A7.3 · phases 2c–4 (library chapters, chapter cards, briefing, outbox, API, web)

## Global Constraints

- The overview's Global Constraints 1–16 apply.
- **Commands:** `/study <goal> <topic>` and `/stop` (D23); `/skill <name> <status>`.
- **Goals:** `dev`, `gate`, `gov` (SSC CGL and banking), `current`, `english`.
- **Revisions** at +1, +7 and +30 days, plus +90 for the exam goals `gate` and `gov` (06 A7.3). Chapters I mark as read get the same schedule from the day I mark them. Sessions auto-close after 4 hours (minutes capped at 240).
- **Check-in buttons:**
  - sleep bands 1 (under 5 h), 2 (5–6 h), 3 (6–7 h), 4 (7–8 h), 5 (8 h or more)
  - energy 1–5
  - mood 1–5
- **Patterns** need at least 7 days in each compared group and are worded as patterns, never as causes.
- **Alerts:** at most 1 per job or check every 6 hours. Alert text names the job and the exception type only, never the message content.

## Review Focus

1. **`/study` while a session is already running** replies with the running session and doesn't start a second. Task 1 `test_start_when_running`.
2. **Forgetting `/stop`** auto-closes the session at 4 hours. Task 1 `test_stale_session_auto_closed`.
3. **Fewer than 7 days of check-ins** shows no pattern, not a misleading one. Task 4 `test_pattern_needs_seven_days_each`.
4. **The server off for 30 hours** catches up once: no duplicate briefing, revisions or alerts. Task 7 `test_catch_up_after_30_hours`.
5. **`/skill` with a name that has no page** replies clearly and writes nothing. Task 5 `test_unknown_skill`.

Also pinned on 2026-11-08:
- **A chapter of a GATE book marked as read** gets four revisions, the last at +90 days. Task 1 `test_chapter_revisions_include_90_for_exam_books`.

---

### Task 1: Study sessions and the 1–7–30 revision calendar

**SEC:** SEC-26

**Files:**
- Create: `src/techradar/planner/__init__.py`, `src/techradar/planner/sessions.py`, `src/techradar/db/migrations/versions/0007_planner.py`
- Modify: `src/techradar/bot/routing.py` (add `study` and `stop`), `src/techradar/worker/tasks.py` (add the hourly `close_stale_sessions_job`)
- Test: `tests/planner/test_sessions.py`

**Interfaces:**
- Produces:
  - `class Goal(StrEnum)`: `DEV="dev"`, `GATE="gate"`, `GOV="gov"`, `CURRENT="current"`, `ENGLISH="english"`
  - **Migration `0007_planner`:**
    - `study_sessions` (`id`, `goal`, `topic` varchar(120), `started_at`, `ended_at` null, `minutes` null, `auto_closed` bool default false)
    - `revisions` (`id`, `goal`, `topic`, `due_date` date, `done_at` null, `session_id` null, `chapter_id` null)
    - `checkins` (`date` primary key, `sleep_band` null, `energy` null, `mood` null)
    - `plans` (`date` primary key, `lines` jsonb)
  - `def parse_study_command(arg: str) -> tuple[Goal, str] | None`. Goal words: `gate`; `gov`, `ssc` or `bank`; `dev`; `current` or `news`; `english`. The topic is the rest of the text (1–120 characters).
  - `async def start_session(session, goal: Goal, topic: str, now: datetime) -> Literal["started","already_running"]`
  - `class StudyStop(BaseModel)`: `minutes: int`, `goal: Goal`, `topic: str`, `revision_dates: list[date]`
  - `async def stop_session(session, now: datetime) -> StudyStop | None`: creates revisions unless the topic already has pending ones
  - `def revision_dates(day: date, goal: Goal) -> list[date]` returns `[day + 1, day + 7, day + 30]`, plus `day + 90` when `goal` is `GATE` or `GOV`
  - `def goal_for_doc(exam_tags: Sequence[str]) -> Goal`: `gate` → `GATE`; `ssc_cgl` or `bank` → `GOV`; otherwise `CURRENT`
  - `async def schedule_chapter_revisions(session, chapter_id: int, read_on: date) -> list[date]`: creates the chapter's revisions (topic = `<book> · <chapter title>`), unless they exist already. Phase 3's `mark_chapter_read` calls it, and its reply becomes `Marked <NN>. <title> as read: <k> cards added. Revisions set for <dates>.`
  - `def join_dates(ds: Sequence[date]) -> str`: `d MMM` values joined with `, ` and ` and ` before the last
  - `async def close_stale_sessions(session, now: datetime) -> int`
  - **Replies (exact):**
    - `Started <GOAL> · <topic>. Send /stop when you finish.`
    - `Already studying <GOAL> · <topic> since <HH:MM>.`
    - `Stopped: <n> min of <GOAL> · <topic>. Revisions set for <dates>.`, with `<dates>` from `join_dates`
    - `No session running.`

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_study_command():
    assert parse_study_command("gate operating systems") == (Goal.GATE, "operating systems")
    assert parse_study_command("bank percentages") == (Goal.GOV, "percentages")
    assert parse_study_command("cooking") is None

def test_revision_dates():
    assert revision_dates(date(2026, 11, 8), Goal.DEV) == [date(2026, 11, 9), date(2026, 11, 15), date(2026, 12, 8)]
    assert revision_dates(date(2026, 11, 8), Goal.GATE)[-1] == date(2027, 2, 6)

def test_join_dates():
    assert join_dates([date(2026, 11, 9), date(2026, 11, 15), date(2026, 12, 8)]) == "9 Nov, 15 Nov and 8 Dec"

@pytest.mark.db
async def test_chapter_revisions_include_90_for_exam_books(session, gate_book_chapter):
    ds = await schedule_chapter_revisions(session, gate_book_chapter.id, date(2026, 11, 8))
    assert len(ds) == 4 and await schedule_chapter_revisions(session, gate_book_chapter.id, date(2026, 11, 8)) == []

@pytest.mark.db
async def test_start_when_running(session):
    await start_session(session, Goal.GATE, "os", NOW)
    assert await start_session(session, Goal.DEV, "x", NOW) == "already_running"

@pytest.mark.db
async def test_stop_creates_revisions(session):
    await start_session(session, Goal.GATE, "os", NOW)
    s = await stop_session(session, NOW + timedelta(minutes=45))
    assert s.minutes == 45 and len(s.revision_dates) == 4             # GATE gets +90

@pytest.mark.db
async def test_stale_session_auto_closed(session):
    await start_session(session, Goal.GATE, "os", NOW)
    assert await close_stale_sessions(session, NOW + timedelta(hours=5)) == 1
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/planner/test_sessions.py -v && uv run pytest -m db tests/planner -v`
Expected: FAIL

- [ ] **Step 3: Implement the migration, sessions module, routing and job**

- [ ] **Step 4: Run the tests**

Run: `docker compose run --rm migrate && uv run pytest tests/planner && uv run pytest -m db tests/planner -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/planner src/techradar/db src/techradar/bot src/techradar/worker tests/planner && git commit -m "feat(planner): study tracker and 1-7-30 revisions"
```

### Task 2: One-tap energy check-in

**SEC:** SEC-26

**Files:**
- Create: `src/techradar/planner/checkin.py`
- Modify: `src/techradar/bot/callbacks.py` (add `sleep`, `energy` and `mood`), `src/techradar/briefing/compose.py` (send the check-in message right after the briefing)
- Test: `tests/planner/test_checkin.py`

**Interfaces:**
- Produces:
  - `def checkin_keyboard() -> list[list[Button]]`: three rows, `sleep:1`–`sleep:5`, `energy:1`–`energy:5`, `mood:1`–`mood:5`, with labels `<5h`, `5–6`, `6–7`, `7–8`, `8+` / `1`…`5`
  - `CHECKIN_TEXT = "How did you sleep, and how's your energy and mood today? (one tap each)"`
  - `async def record_checkin(session, day: date, field: Literal["sleep","energy","mood"], value: int) -> None`: upsert; raises `ValueError` outside 1–5
  - The bot's answer to each tap: `Noted.`

- [ ] **Step 1: Write the failing tests**

```python
def test_checkin_keyboard_data():
    kb = checkin_keyboard()
    assert [b.data for b in kb[0]] == [f"sleep:{i}" for i in range(1, 6)] and len(kb) == 3

@pytest.mark.db
async def test_record_checkin_upserts(session):
    await record_checkin(session, TODAY, "sleep", 2); await record_checkin(session, TODAY, "sleep", 4)
    assert await get_checkin(session, TODAY) == {"sleep_band": 4, "energy": None, "mood": None}

@pytest.mark.db
async def test_record_checkin_rejects_out_of_range(session):
    with pytest.raises(ValueError): await record_checkin(session, TODAY, "mood", 9)
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/planner/test_checkin.py -v && uv run pytest -m db tests/planner/test_checkin.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module and callbacks; send the check-in after the briefing**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/planner src/techradar/bot src/techradar/briefing tests/planner && git commit -m "feat(planner): one-tap energy check-in"
```

### Task 3: Daily plan in the briefing

**Files:**
- Create: `src/techradar/planner/plan.py`
- Modify: `src/techradar/briefing/compose.py` (`render_briefing` adds a `TODAY'S PLAN` block at the top of the first message), `src/techradar/api/schemas.py` (`UserSettings` gains `exam_priority: list[Goal]`, `exam_dates: dict[str, date]`, `weekly_targets_min: dict[Goal, int]`), `tests/briefing/test_compose.py`
- Test: `tests/planner/test_plan.py`

**Interfaces:**
- Produces:
  - **Settings defaults (changeable in Settings):**
    - `exam_priority = [Goal.GOV, Goal.GATE]`
    - `exam_dates = {}`
    - `weekly_targets_min = {DEV: 600, GATE: 300, GOV: 420, CURRENT: 105, ENGLISH: 140}`
  - `def compose_plan(today: date, *, due_revisions: Sequence[RevisionRow], due_cards: int, quiz_ready: bool, minutes_this_week: Mapping[Goal, int], targets: Mapping[Goal, int], priority: Sequence[Goal], final_30_exam: str | None = None) -> list[str]`. The lines, in order:
    1. `⏳ Final 30 days: <exam>` (only when `final_30_exam` is set)
    2. `📰 Radar (10–15 min)`
    3. `📝 Current affairs quiz: 10 MCQs` (only when `quiz_ready`)
    4. `🔁 Reviews due: <n> flashcards` + ` + <k> topic revisions` (each part only when non-zero)
    5. `🎓 <GOAL>: <first due revision topic of that goal or "next topic"> (45 min)`, for the goal with the largest `1 - minutes/target` deficit, ties broken by `priority`
    6. `🔤 English: 5 new words + 10 grammar questions`
  - `plan_lines` are stored in `plans` and passed to `Briefing.plan_lines`.

- [ ] **Step 1: Write the failing tests**

```python
def test_plan_orders_and_picks_most_behind_goal():
    lines = compose_plan(TODAY, due_revisions=[REV_GATE_OS], due_cards=18, quiz_ready=True,
                         minutes_this_week={Goal.GATE: 30, Goal.GOV: 400}, targets=TARGETS, priority=[Goal.GOV, Goal.GATE])
    assert lines == ["📰 Radar (10–15 min)", "📝 Current affairs quiz: 10 MCQs", "🔁 Reviews due: 18 flashcards + 1 topic revisions",
                     "🎓 GATE: os (45 min)", "🔤 English: 5 new words + 10 grammar questions"]

def test_plan_final_30_first_line():
    assert compose_plan(TODAY, due_revisions=[], due_cards=0, quiz_ready=False, minutes_this_week={}, targets=TARGETS,
                        priority=[Goal.GOV], final_30_exam="SSC CGL")[0] == "⏳ Final 30 days: SSC CGL"

def test_briefing_shows_plan_block_first(): ...   # render_briefing(...)[0] starts with header then "TODAY'S PLAN"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/planner/test_plan.py tests/briefing -v`
Expected: FAIL

- [ ] **Step 3: Implement `plan.py` and the briefing and settings changes**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/planner src/techradar/briefing src/techradar/api tests && git commit -m "feat(planner): daily plan in the morning briefing"
```

### Task 4: Progress screen and weekly review

**SEC:** SEC-24, SEC-27

**Files:**
- Create: `src/techradar/planner/progress.py`, `src/techradar/api/routes/progress.py`, `apps/web/src/app/(app)/progress/page.tsx`, `apps/web/src/components/progress/{GoalBars,AccuracyLine,CheckinHeatmap}.tsx`
- Modify: `src/techradar/worker/tasks.py` (add `weekly_review_job`, Sundays at 19:00), `tests/web_mock.py`
- Test: `tests/planner/test_progress.py`, `apps/web/tests/progress.spec.ts`

**Interfaces:**
- Produces:
  - `def week_bounds(any_day: date) -> tuple[date, date]`: Monday to Sunday (Asia/Kolkata dates)
  - `class Pattern(BaseModel)`: `text: str`, `days_low: int`, `days_high: int`, `diff_points: float`
  - `def sleep_accuracy_pattern(days: Sequence[DayStat]) -> Pattern | None`, where `DayStat(date, sleep_band, quiz_accuracy)`:
    - Low group: `sleep_band ≤ 2`; high group: `sleep_band ≥ 3`.
    - Returns `None` unless each group has at least 7 days with a quiz.
    - Text: `Your quiz accuracy is <n> points <lower|higher> after nights under 6 hours (<d> days of data).`
  - `class WeekProgress(BaseModel)`: `minutes_by_goal`, `targets`, `streak_days: int`, `quiz_accuracy: float | None`, `cards_reviewed: int`, `pattern: Pattern | None`
  - `async def week_progress(session, week_start: date) -> WeekProgress`
  - `GET /v1/progress?week=YYYY-Www` returns `WeekProgress`
  - `weekly_review_job`: an outbox summary, plus the vault page `reviews/<YYYY>-W<ww>.md` (`generated: true`)
  - **Progress screen:** planned-versus-actual bars per goal, an accuracy line, a check-in heatmap, streak and pattern cards

- [ ] **Step 1: Write the failing tests**

```python
def test_week_bounds_monday_to_sunday():
    assert week_bounds(date(2026, 11, 8)) == (date(2026, 11, 2), date(2026, 11, 8))

def test_pattern_needs_seven_days_each():
    assert sleep_accuracy_pattern(days(low=6, high=10)) is None

def test_pattern_difference_and_wording():
    p = sleep_accuracy_pattern(days(low=7, high=7, low_acc=0.60, high_acc=0.72))
    assert p.diff_points == pytest.approx(12.0) and p.text.startswith("Your quiz accuracy is 12 points lower")
```

```ts
test("progress renders bars and pattern", async ({ page }) => {
  await page.goto("/progress"); await expect(page.getByRole("img", { name: /minutes per goal/i })).toBeVisible();
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/planner/test_progress.py -v && cd apps/web && pnpm playwright test tests/progress.spec.ts`
Expected: FAIL

- [ ] **Step 3: Implement the progress module, API route, job and screen**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar apps/web tests && git commit -m "feat(progress): weekly progress, patterns and review"
```

### Task 5: Skill map updates

**SEC:** SEC-24, SEC-27

**Files:**
- Create: `src/techradar/vault/frontmatter.py`, `src/techradar/api/routes/skills.py`
- Modify: `src/techradar/bot/routing.py` (add `skill`), `apps/web/src/app/(app)/progress/page.tsx` (skill map table)
- Test: `tests/vault/test_frontmatter.py`, `tests/bot/test_skill.py`

**Interfaces:**
- Produces:
  - `SKILL_STATUSES = ("not_started", "learning", "built")`
  - `def update_front_matter(md: str, updates: Mapping[str, Any], allowed_keys: frozenset[str]) -> str`: keeps the body byte for byte, rewrites the front matter with `yaml.safe_dump`, raises `ValueError` for a key not in `allowed_keys`
  - `async def set_skill_status(vault_root: Path, name: str, status: str, today: date) -> str`:
    - Looks up `skills/<slugify(name)>.md`.
    - Sets `status` and `updated`.
    - Returns `Updated <name>: <status>.`, or `No skill page called <name>.`, or `Status must be not_started, learning or built.`
  - `PUT /v1/skills/{slug}` takes `{status}` and uses the same function.

- [ ] **Step 1: Write the failing tests**

```python
def test_front_matter_update_keeps_body():
    md = "---\nkind: skill\nstatus: not_started\n---\n# FastAPI\nmy notes\n"
    out = update_front_matter(md, {"status": "learning"}, frozenset({"status", "updated"}))
    assert out.endswith("# FastAPI\nmy notes\n") and "status: learning" in out

def test_front_matter_rejects_other_keys():
    with pytest.raises(ValueError): update_front_matter("---\na: 1\n---\n", {"kind": "x"}, frozenset({"status"}))

async def test_unknown_skill(tmp_vault):
    assert await set_skill_status(tmp_vault, "Cobol", "learning", TODAY) == "No skill page called Cobol."
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/vault/test_frontmatter.py tests/bot/test_skill.py -v`
Expected: FAIL

- [ ] **Step 3: Implement the module, route, bot command and table**

- [ ] **Step 4: Run the tests**

Run: same as Step 2.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar apps/web tests && git commit -m "feat(skills): update skill map from Telegram and the web"
```

### Task 6: Failure alerts and health checks

**SEC:** SEC-14, SEC-32

**Files:**
- Create: `src/techradar/ops/alerts.py`, `src/techradar/ops/health.py`
- Modify: `src/techradar/worker/tasks.py` (wrap jobs with `alert_on_failure`; add the hourly `health_job`), `infra/backup/backup.sh` (write `data/status/backup.json` as `{"ok": bool, "at": iso}`), `compose.yaml` (worker mounts `./data/status` read-only)
- Test: `tests/ops/test_alerts.py`, `tests/ops/test_health.py`

**Interfaces:**
- Produces:
  - `ALERT_WINDOW = timedelta(hours=6)`
  - `async def raise_alert(session, owner_chat_id: int, key: str, text: str, now: datetime) -> bool`: deduplicated per `key` within `ALERT_WINDOW` (`alerts` table); returns whether a message was enqueued
  - `def alert_on_failure(name: str) -> Callable`: a decorator that, on an exception, calls `raise_alert(key=f"job:{name}", text=f"⚠️ Job {name} failed: {type(e).__name__}")` and re-raises
  - `class HealthReport(BaseModel)`: `problems: list[tuple[str, str]]`, as `(key, text)` pairs
  - `def check_health(*, disk_free_pct: float, last_fetch_ok: datetime | None, enabled_sources: int, backup_status: dict | None, ollama_ok: bool, now: datetime) -> HealthReport`. The rules and messages:
    - Disk below 15%: `⚠️ Disk free is <n>%.`
    - Last successful fetch more than 6 h ago while sources are enabled: `⚠️ No news fetched for <h> hours.`
    - Backup status missing, older than 36 h, or not ok: `⚠️ Backup hasn't succeeded in 36 hours.`
    - Ollama down: `⚠️ Local models are down.`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.db
async def test_alert_deduplicated_within_window(session):
    assert await raise_alert(session, 42, "job:x", "t", NOW)
    assert not await raise_alert(session, 42, "job:x", "t", NOW + timedelta(hours=5))
    assert await raise_alert(session, 42, "job:x", "t", NOW + timedelta(hours=7))

def test_health_rules():
    r = check_health(disk_free_pct=10, last_fetch_ok=NOW - timedelta(hours=7), enabled_sources=3,
                     backup_status={"ok": True, "at": (NOW - timedelta(hours=40)).isoformat()}, ollama_ok=False, now=NOW)
    assert {k for k, _ in r.problems} == {"disk", "fetch", "backup", "ollama"}

def test_alert_text_has_no_exception_message():
    ...  # failing job raising ValueError("secret detail") → enqueued text == "⚠️ Job demo failed: ValueError"
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run pytest tests/ops -v && uv run pytest -m db tests/ops -v`
Expected: FAIL

- [ ] **Step 3: Implement the alerts, health module, job wrapper and backup status file**

- [ ] **Step 4: Run the tests and shellcheck**

Run: same as Step 2, then `shellcheck infra/backup/backup.sh`.
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/techradar/ops src/techradar/worker infra/backup compose.yaml tests/ops && git commit -m "feat(ops): job failure alerts and hourly health checks"
```

### Task 7: Catch-up test and gate 5

**SEC:** a re-check of all controls; D19

**Files:**
- Create: `tests/e2e/test_catch_up.py` (marker `db`)
- Modify: `Makefile` (add `gate-5`), `docs/security/gates.md`

**Interfaces:**
- Produces:
  - **`test_catch_up_after_30_hours`:** with a frozen clock, the worker stops at T and starts at T+30h, then all periodic jobs run once. It asserts:
    - each enabled source is fetched once
    - no briefing is sent, because it's past the grace period
    - revisions that fell due in the gap appear in the next plan
    - one alert per key
  - **`make gate-5`:**
    1. `gate-4`
    2. `pytest tests/planner tests/ops`
    3. `pytest -m db tests/planner tests/ops tests/e2e`
    4. Playwright `progress.spec.ts`
    5. Print the signing reminder.

- [ ] **Step 1: Write the failing catch-up test**

- [ ] **Step 2: Run it to see it fail**

Run: `uv run pytest -m db tests/e2e/test_catch_up.py -v`
Expected: FAIL

- [ ] **Step 3: Fix any job that runs twice or misses a catch-up**

- [ ] **Step 4: Run the gate on the server**

Run: `make gate-5`
Expected: every step passes.

- [ ] **Step 5: Commit and sign**

```bash
git add tests/e2e Makefile docs/security/gates.md && git commit -m "docs(security): catch-up verified, gate 5 passed"
```
