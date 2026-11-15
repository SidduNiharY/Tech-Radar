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

## Phase 5 Task 3: Daily plan in the briefing · 55bbed2 · 2026-11-15
- Built: planner/plan.py (compose_plan), api/schemas.py UserSettings fields
- Tests: 3 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: daily plan lines generated and saved to `plans` table; displayed in morning briefing
- Old code removed: none
- Open questions: none

## Phase 5 Task 4: Progress screen and weekly review · a2ff20d · 2026-11-15
- Built: planner/progress.py (week_bounds, sleep_accuracy_pattern, week_progress, run_weekly_review)
- Tests: 3 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: GET `/v1/progress` route, Next.js Progress UI; background job `weekly_review_job` (Sundays at 19:00)
- Old code removed: none
- Open questions: none

## Phase 5 Task 5: Skill map updates · a30076a · 2026-11-15
- Built: vault/frontmatter.py (update_front_matter, set_skill_status)
- Tests: 9 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: bot command `/skill <name> <status>`, PUT `/v1/skills/{slug}` route
- Old code removed: none
- Open questions: none

## Phase 5 Task 6: Failure alerts and health checks · 079a748 · 2026-11-15
- Built: ops/alerts.py (raise_alert, alert_on_failure), ops/health.py (check_health, HealthReport)
- Tests: 8 unit pass
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: job failure decorator wrapping Procrastinate tasks; hourly health_job; backup.sh status file and compose mount
- Old code removed: none
- Open questions: none

## Phase 5 handed back · 079a748

## Phase 6: Voice Coach v1 and English Practice · fe8fb58 · 2026-11-15
- Built:
  - Models: `VoiceSession`, `VoiceMetrics`, `PronunciationScore`, `WritingFeedback`, `Story`, `StoryDraft`, `Listening`, `Reflection`, `VoiceNotice` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0008_voice.py` revising `0007_planner`
  - Voice intake & audio: `voice/intake.py` (duration/size limits, OggS magic check, 0o640 file save), `voice/audio.py` (decode_audio, compute_peaks)
  - Transcription & library video: `voice/transcribe.py` (Word, Transcript, Transcriber Protocol, no_speech), `voice/library_audio.py` (offset_words, SlideText, TimedChapter, chapters_by_time)
  - Metrics & pronunciation: `voice/metrics.py` (compute_metrics, SpeechMetrics, fillers, long pauses, TTR, overused words), `voice/align.py` (CTC Viterbi forced alignment, phone_scores, to_vocab_ids), `voice/pronounce.py` (expected_ipa, PhonemeModel Protocol, WordScore, score_words)
  - Voice feedback & jobs: `voice/feedback.py` (choose_fixes top 3, phrase_feedback, render_voice_report), `voice/speak.py` (Speaker Protocol, KokoroOnnxSpeaker), `voice/jobs.py` (analyse_voice, cleanup_voice with 24h retention)
  - English practice: `english/grammar_check.py` (check_grammar, GrammarIssue, RULE_MAP), `english/writing.py` (Rubric, WritingFeedback, feedback_on_text, render_writing_feedback, route_and_validate_polish), `english/stories.py` (STAR_FIELDS, story_step), `english/reading.py` (reading_quiz), `english/listening.py` (KeyPoints, Coverage, render_coverage), `english/reflection.py` (save_reflection), `voice/practice_time.py` (reminder_due)
  - Security checks: `scripts/check_model_files.py` (banning .pt/.pth/.pkl/.ckpt and gating .bin)
- Tests: 37 unit tests pass across `tests/voice`, `tests/english`, `tests/scripts` (4 db tests marked)
- Not run: `docker compose run --rm migrate` and live GPU tests (needs the server)
- Differs from the plan: none
- Wiring for Claude: `voice-worker` service (GPU, whisper, kokoro, wav2vec2), `languagetool` container on `tools` network, Telegram voice handler & `keep_voice` callback, API voice routes & Next.js Voice Report screen, `make gate-6`
- Old code removed: `src/techradar/voice/fluency.py`, `src/techradar/voice/grammar.py`, and obsolete tests
- Open questions: none

## Phase 6 handed back · fe8fb58















