# Implementation log (Antigravity's basic work)

One entry per finished task, newest at the bottom. The format and the rules are in [`implementations.md`](implementations.md) section 12. Claude reads this file to review and wire each phase; statuses in `TODO.md` change only after that review.

A task that could not be done gets an entry too, with `BLOCKED` in the heading and the reason.

<!-- Entry format:

## Phase 3 Task 5: Quiz, flashcards, mistakes · <commit sha> · <date>
- Built:
- Tests:
- Not run:
- Differs from the plan:
- Wiring for Claude:
- Old code removed:
- Open questions:

-->

## Phase 3 Task 1: Morning briefing composer, Phase 3 models and migration 0005 · 478f70b · 2026-11-15
- Built: src/techradar/db/models.py (added Briefing, Take, MCQ, QuizAttempt, Flashcard, Mistake, Vocab, GrammarItem, ExamWatch, Alert, ReviewDecision), src/techradar/db/migrations/versions/0005_practice.py, src/techradar/briefing/compose.py (run_briefing, BriefingResult)
- Tests: 14 briefing unit tests pass; 2 db orm tests pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: worker/tasks.py needs `briefing_job` (queue io, every 15 minutes) calling run_briefing
- Old code removed: none
- Open questions: none

## Phase 3 Task 5: Quiz, flashcards, mistakes · 0bda5a8 · 2026-11-15
- Built: practice/quiz.py, practice/flashcards.py, practice/mistakes.py
- Tests: 19 unit pass; 4 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: routing `quiz`, `cards`; callbacks `ans`, `rate`; jobs quiz_job, cards_job, mistakes_page_job
- Old code removed: practice/quiz.py classes TwoModelKeyChecker, DailyPracticeLimits
- Open questions: none

## Phase 3 Task 2: "My take" replies · e420b38 · 2026-11-15
- Built: briefing/takes.py
- Tests: 6 unit pass; 2 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot handler for replies to briefing messages; extracts `take_text`, calls `save_take(session, briefing_id, take_text, today, vault_root)`
- Old code removed: none
- Open questions: none

## Phase 3 Task 4: Facts-first MCQs with two-family checking · 055ab14 · 2026-11-15
- Built: practice/mcq.py, evals/mcq/export.py
- Tests: 22 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: background job `mcq_job` calling `run_make_mcqs(session, maker_model, checker_model, today)`; evaluation harness `export_eval_dataset`
- Old code removed: none
- Open questions: none

## Phase 3 Task 6: Grammar set and vocabulary from reading · 7136ecf · 2026-11-15
- Built: practice/grammar.py, practice/vocab.py (WordAnalyzer Protocol with pure Python DefaultWordAnalyzer)
- Tests: 26 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: wordfreq / spacy abstracted behind WordAnalyzer Protocol to maintain zero unvetted dependencies in core
- Wiring for Claude: bot commands `/grammar`, `/vocab`; daily schedule jobs; server can inject SpacyWordAnalyzer via WordAnalyzer Protocol
- Old code removed: none
- Open questions: none

## Phase 3 Task 7: Exam notification watcher · fbb52a8 · 2026-11-15
- Built: alerts/watcher.py
- Tests: 6 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: polling job `exam_poll_job` every 15 min; feeds outbound alert queue with deduplication via `alerts` table
- Old code removed: none
- Open questions: none

## Phase 3 Task 5b: Mark chapter as read and chapter cards · 88385cd · 2026-11-15
- Built: practice/chapter_cards.py (render_chapter_list, make_chapter_cards, mark_chapter_read, run_make_chapter_cards)
- Tests: 8 unit pass; 1 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot callbacks `chap`, `read`, `src`; background job `make_chapter_cards_job`
- Old code removed: none
- Open questions: none

## Phase 3 Task 8: Monthly capsule and review inbox · 3fe6778 · 2026-11-15
- Built: briefing/capsule.py, pipeline/review.py
- Tests: 4 unit pass; 2 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot command `/inbox`, callbacks `keep`, `drop`; background job `capsule_job` at 07:00 on the 1st
- Old code removed: none
- Open questions: none

## Phase 3 Task 8b: Outdated facts retire their cards and MCQs · 06d0204 · 2026-11-15
- Built: practice/supersede.py (apply_fact_change, run_fact_changes, fact_changes_job)
- Tests: 2 unit pass; 2 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: background job `fact_changes_job` (queue `io`, every 15 minutes)
- Old code removed: none
- Open questions: none

## Phase 3 handed back · 1bcf1ec

## Phase 4 Task 2: Web app models, schemas, and migration 0006 · 4f257be · 2026-11-15
- Built: api/schemas.py (TodayResponse, AskRequest, AnswerStatus, CardOut, QuizQuestion, AnswerOutcome, ModelsStatus, UserSettings, Ticket), db/models.py (UserSettings, PendingAction, Briefing.items), db/migrations/versions/0006_web.py
- Tests: 6 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: FastAPI endpoints in `src/techradar/api/routes/{today,ask,practice,quiz,settings,models,tickets}.py`; OpenAPI export script `scripts/export_openapi.py`
- Old code removed: none
- Open questions: none

## Phase 4 handed back · 4f257be

## Phase 5 Task 1: Study sessions and 1-7-30 revision calendar · dbfcb29 · 2026-11-15
- Built: planner/sessions.py (Goal, revision_dates, parse_study_command, join_dates, goal_for_doc, start_session, stop_session, schedule_chapter_revisions, close_stale_sessions), models.py (StudySession, Revision, Checkin, Plan), migrations/0007_planner.py
- Tests: 4 unit pass; 4 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot commands `/study`, `/stop`; background job `close_stale_sessions_job` (hourly)
- Old code removed: none
- Open questions: none

## Phase 5 Task 2: One-tap energy check-in · bcfcfc9 · 2026-11-15
- Built: planner/checkin.py (checkin_keyboard, record_checkin, get_checkin, CHECKIN_TEXT)
- Tests: 1 unit pass; 2 db written, collect, not run
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot callbacks `sleep`, `energy`, `mood`; send check-in message after morning briefing
- Old code removed: none
- Open questions: none












