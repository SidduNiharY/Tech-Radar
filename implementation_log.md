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

## Phase 7: Understanding and World · a73dc76 · 2026-11-15
- Built:
  - Models: `DeepDive`, `GlossaryTerm`, `Timeline`, `Prediction`, `EconSeries`, `FactCheck` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0009_world.py` revising `0008_voice`
  - Night foundations: `night/foundations.py` (`wikipedia_url`, `queue_background`, `GENERATED_START`, `GENERATED_END`, `replace_generated_block`, `FoundationSection`, `fill_foundation`), `fetcher/wikipedia.py` (`wikipedia_url`)
  - Deep dives: `night/deep_dive.py` (`ClusterStat`, `pick_topic`, `DDSection`, `DeepDive`, `write_deep_dive`)
  - Glossary, timelines, causal chains: `night/glossary.py` (`glossary_candidates`, `GlossaryEntry`, `write_glossary_entry`), `night/timelines.py` (`TimelineEntry`, `timeline_entries`, `write_timeline`), `night/chains.py` (`CausalChain`, `sanitize_label`, `chain_to_mermaid`)
  - Politics: `pipeline/politics.py` (`POLITICS_SYSTEM`, `Opinion`, `FactClaim`, `PoliticsView`, `keep_attributed`, `render_opinion_sections`)
  - Predictions: `world/predictions.py` (`parse_predict`, `render_predictions_context`, `get_due_predictions`, `record_prediction`, `record_outcome`, `sync_predictions_vault`)
  - Economy: `world/econ.py` (`SERIES`, `SeriesSpec`, `extract_series_value`, `parse_worldbank`, `parse_econ_command`, `change_sentence`)
- Tests: 90 unit tests pass across `tests/night`, `tests/world`, `tests/pipeline`, `tests/fetcher` (16 db tests collect)
- Not run: `docker compose run --rm migrate` (needs the server)
- Differs from the plan: none
- Wiring for Claude: `foundation_fill_job`, `deep_dive_job`, `prediction_reminder_job`; SearXNG service & allowlists; bot `/predict`, `/econ`, `/check` routing and callbacks; API `/v1/world/econ` route and Next.js World screen
- Old code removed: `src/techradar/practice/predictions.py`, `src/techradar/world/causality.py`, `src/techradar/world/economy.py`, `src/techradar/world/glossary.py`, and obsolete tests
- Open questions: none

## Phase 7 handed back · a73dc76

## Phase 8: Exams (Basic Work) · 3e04dfe · 2026-11-15
- Built:
  - Models: `SyllabusTopic`, `PyqQuestion`, `DrillAttempt`, `MockResult`, `Cutoff`, `TopicWeight`, `TopicSource` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0010_exams.py` revising `0009_world`
  - Task 1 Syllabus: `src/techradar/exams/syllabus.py` (`parse_topics`, `sync_syllabus`, `TopicCoverage`, `coverage`, `coverage_for`), tested in `tests/exams/test_syllabus.py`
  - Task 2 PYQs: `src/techradar/exams/pyq.py` (`QuestionChunk`, `split_questions`, `KeyEntry`, `parse_answer_key`, `check_answer`, `suggest_topic`), tested in `tests/exams/test_pyq.py`
  - Task 2b Sources: `src/techradar/exams/sources.py` (`candidate_topics`, `suggest_for_chapter`, `suggest_topic_sources`, `decide_source`, `source_status`, `only_source_id`, `topics_without_sources`, `run_suggest_topic_sources`, `run_sources_digest`), tested in `tests/exams/test_sources.py`
  - Task 3 Drills: `src/techradar/exams/drills/` (`DrillItem`, `daily_set`, `typing_passage`, `score_typing`, and 18 code-generators for quant, reasoning, and speed maths with exact oracles), tested in `tests/exams/test_drills.py` (200 random seeds per generator)
  - Task 4 Deliver: `src/techradar/exams/deliver.py` (`record_drill`, `render_drill_summary`), tested in `tests/exams/test_deliver.py`
  - Task 5 Mocks: `src/techradar/exams/mocks.py` (`SectionScore`, `MockScore`, `extract_mock_regex`, `numbers_present`, `extract_mock`, `render_mock_reply`), tested in `tests/exams/test_mocks.py`
  - Task 6 Weights: `src/techradar/exams/weights.py` (`CutoffRow`, `WeightRow`, `TopicWeight`, `import_cutoffs`, `import_weightage`, `gate_weights`), tested in `tests/exams/test_weights.py`
  - Task 6b Answer Keys: `src/techradar/exams/answer_keys.py` (`load_capture_pattern`, `matching_links`, `render_answer_key_notice`), tested in `tests/exams/test_answer_keys.py`
  - Task 7 Final 30: `src/techradar/exams/final30.py` (`final_30`, `mini_mock`, `write_formula_sheet`, `capsule_bundle`), `src/techradar/planner/plan.py` (`final_30_exam` parameter), tested in `tests/exams/test_final30.py`
- Tests: 83 tests pass across `tests/exams` and planner integration
- Not run: `docker compose run --rm migrate` (needs server)
- Differs from the plan: none
- Wiring for Claude: bot `/drill` command, callbacks `drill:<n>:<0-3>`, `srcok:<id>`, `srcno:<id>`; inbox routing for `gate/<year>/`, `cutoffs/`, `weightage/`; `syllabus_sync_job`, `suggest_topic_sources_job`, `sources_digest_job`, `formula_sheets_job`; parser image sandbox integration (`parser/image.py`); API `/v1/exams` routes and Exams web screen
- Old code removed: in-memory `SyllabusTree` and `SyllabusNode` replaced with DB-backed schema
- Open questions: none

## Phase 8 handed back · 3e04dfe

## Phase 9: Study Smarter and Live Voice (Basic Work) · be8e103 · 2026-11-15
- Built:
  - Models: `GroupMember`, `GroupPoll`, `GroupAnswer`, `LiveSession` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0011_live_group.py` revising `0010_exams`
  - Task 2 Study Group: `src/techradar/group/group.py` (`LeaderboardEntry`, `calculate_leaderboard`, `render_leaderboard`, `leaderboard`, `member_hash`, `group_allowed`, `GROUP_MESSAGE_KINDS`), tested in `tests/group/test_group.py`
  - Task 5 Voice Pitch: `src/techradar/voice/pitch.py` (`PitchFeedback`, `pitch_contour`, `compare_pitch_contours`), tested in `tests/voice/test_pitch.py`
  - Task 6 Live Briefs: `src/techradar/voice_live/briefs.py` (`build_live_brief`, `HR_QUESTIONS`, `BANK_PANEL_QUESTIONS`, `SessionBrief`, `build_brief`), `src/techradar/night/know_yourself.py` (`generate_user_portrait`, `know_yourself`), tested in `tests/voice_live/test_briefs.py` and `tests/night/test_know_yourself.py`
- Tests: 25 unit tests pass across `tests/group`, `tests/voice/test_pitch.py`, `tests/voice_live`, and `tests/night`
- Not run: `docker compose run --rm migrate` (needs server)
- Differs from the plan: none
- Wiring for Claude: group allowlists, privacy salt, Telegram group message handlers; `voice-live` container wiring; `live_jobs.py`; live audio capture
- Old code removed: none
- Open questions: none

## Phase 9 handed back · be8e103

## Phase 10: Models Admin and Tech Extras (Basic Work) · 88017c6 · 2026-11-15
- Built:
  - Models: `ModelRegistry`, `ModelChange`, `ModelTest`, `ModelRequest`, `PlaygroundRun`, `TrendCount` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0012_models.py` revising `0011_live_group`
  - Task 3 Fit: `src/techradar/models/fit.py` (`ModelVramEstimate`, `estimate_vram_and_fit`, `kv_estimate`, `estimate_fit`), tested in `tests/models/test_fit.py`
  - Task 4 Eval Bench: `src/techradar/models/bench.py` (`BenchScore`, `score_bench_run`, `passes_worker`, `passes_checker`, `passes_embed`, `passes_night`), `evals/sets/README.md`, `evals/sets/gate_cs.example.yaml`, tested in `tests/models/test_bench.py`
  - Task 6 Release Digest: `src/techradar/digest/releases.py` (`ReleaseItem`, `Update`, `parse_release_payload`, `format_release_digest`, `render_digest`, `parse_uv_lock`, `parse_pnpm_lock`, `compare`), tested in `tests/digest/test_releases.py`
  - Task 7 Emerging Trends: `src/techradar/digest/trends.py` (`TopicTrend`, `Rising`, `normalise_term`, `rising`, `rank_emerging_topics`, `format_trends_digest`), tested in `tests/digest/test_trends.py`
- Tests: 38 unit tests pass across `tests/models` and `tests/digest`
- Not run: `docker compose run --rm migrate` (needs server)
- Differs from the plan: none
- Wiring for Claude: GPU stats collection service; model pull/switch/rollback jobs; package release fetching and `tracked.yaml` allowlists; `rag/retrieve.py` trend boosting
- Old code removed: none
- Open questions: none

## Phase 10 handed back · 88017c6

## Phase 11: Feedback and Self-Improvement (Basic Work) · cd3a912 · 2026-11-15
- Built:
  - Models: `Feedback`, `ActionLog`, `Edit`, `Weight`, `PreferenceRule`, `RegressionCase`, `ImprovementLog`, `StyleProfile`, `TopicMastery`, `LikedExample`, `PreferencePair`, `ImprovementReport` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0013_feedback.py` revising `0012_models`
  - Task 2 Signals & Actions: `src/techradar/feedback/__init__.py`, `src/techradar/feedback/signals.py` (`Signal`, `TargetKind`, `TARGET_CODES`, `BUTTONS`, `feedback_buttons`, `record_feedback`), `src/techradar/feedback/actions.py` (`log_action`, `infer_skips`), tested in `tests/feedback/test_signals.py`
  - Task 3 Feedback Edits: `src/techradar/feedback/edits.py` (`EditMetrics`, `compare_edit`, `diff_ratio`, `generate_critique_signals`, `snapshot_path`, `save_snapshot`, `load_snapshot`, `record_edit`), tested in `tests/feedback/test_edits.py`
  - Task 4 Feedback Weights: `src/techradar/feedback/weights.py` (`STEP`, `bounded`, `effective`, `score`, `is_favourite`, `pick_outside_usual`, `apply_signal`), tested in `tests/feedback/test_weights.py`
  - Task 5 Pattern Detection: `src/techradar/feedback/patterns.py` (`Mode`, `Evidence`, `StyleProposal`, `WeightProposal`, `ContentProposal`, `PatternCandidate`, `find_patterns`, `run_find_patterns`, `find_recurring_patterns`), tested in `tests/feedback/test_patterns.py`
  - Task 6 Feedback Report: `src/techradar/feedback/rules.py` (`StyleRule`, `Pick`, `Picks`, `choose_and_word`), `src/techradar/feedback/report.py` (`verify_evidence`, `render_report`, `render_feedback_report`), tested in `tests/feedback/test_rules.py` and `tests/feedback/test_report.py`
  - Task 7 Profiles: `src/techradar/profile/__init__.py`, `src/techradar/profile/style.py` (`TEMPLATES`, `INVARIANT_LINE`, `render_profile_block`, `mode_for`), `src/techradar/profile/mastery.py` (`mastery_level`, `mastery_line`), `src/techradar/profile/setup.py` (`SETUP_QUESTIONS`, `get_setup_questions`, `setup_buttons`, `parse_setup_choice`), tested in `tests/profile/test_profiles.py`
  - Task 8 Regression & Tuning: `src/techradar/feedback/regression.py` (`RegressionReport`, `normalize_sentence`, `save_regression_case`, `run_regression`), `src/techradar/feedback/search_tuning.py` (`tune_book`), tested in `tests/feedback/test_regression.py`
  - Task 9 Feedback Pairs: `src/techradar/feedback/pairs.py` (`VARIANTS`, `pair_due`, `make_pair`, `format_pair_message`, `create_pair`, `record_pair_choice`), tested in `tests/feedback/test_pairs.py`
- Tests: 43 unit tests pass across `tests/feedback`, `tests/profile`, and DB schema verification
- Not run: `docker compose run --rm migrate` (needs server)
- Differs from the plan: none
- Wiring for Claude: bot `/improvements` and `/setup` commands and callbacks (`rule_ok`, `rule_no`, `undo`, `pair`); `weekly_report_job`, `find_patterns_job`, `tune_books_job`; API `/v1/feedback` and `/v1/profile` routes; Next.js profile page with confirmed deletes and undo
- Old code removed: none
- Open questions: none

## Phase 11 handed back · cd3a912

## Phase 12: Jarvis Assistant Router & Skills (Basic Work) · 0b89b69 · 2026-11-15
- Built:
  - Models: `JarvisSession`, `JarvisTurn`, `JarvisWrite`, `JarvisGreeting`, `GpuLease` in `src/techradar/db/models.py`
  - Migration: `src/techradar/db/migrations/versions/0014_jarvis.py` revising `0013_feedback`
  - Task 8 The Ten Read Skills: Pure functions in `src/techradar/jarvis/skill_impl/` returning spoken text (`briefing.py`, `practice.py`, `exams.py`, `voice.py`, `world.py`, `library.py`, `search.py`, `planner.py`, `status.py`, `help.py`), tested in `tests/jarvis/test_skills.py`
  - Task 9 Jarvis Greeting: `src/techradar/jarvis/greeting.py` (`is_quiet_hours`, `suggest_next_actions`, `prepare_greeting`, `run_prepare_greeting`), tested in `tests/jarvis/test_greeting.py`
- Tests: 77 unit tests pass across `tests/jarvis` and DB schema verification
- Not run: `docker compose run --rm migrate` (needs server)
- Differs from the plan: none
- Wiring for Claude: Jarvis write actions execution, tickets, and fast/slow LLM router; `greeting_job`; Jarvis web screen and floating orb
- Old code removed: none
- Open questions: none

## Phase 12 handed back · 0b89b69
















