"""Task names for background worker jobs."""

ASK = "ask"
SAVE_ANSWER = "save_answer"

# --- Phase 3 ---
SAVE_TAKE = "save_take"
QUIZ = "quiz"
CARDS = "cards"
MISTAKES_PAGE = "mistakes_page"
MAKE_CHAPTER_CARDS = "make_chapter_cards"
GRAMMAR_SET = "grammar_set"
# Phase 3 Task 3: links, PDFs and pasted text from the owner (the bot defers, the worker does)
OWNER_LINK = "owner_link"
OWNER_FILE = "owner_file"

# The queue of every night-window job (Phase 7 Task 1). One worker serves it with concurrency 1,
# so two heavy night jobs never share the GPU.
NIGHT_QUEUE = "night"

# --- Phase 7 ---
PREDICTIONS_SYNC = "predictions_sync_job"

# --- Phase 6: English practice ---
POLISH = "polish_job"
ESSAY_REPLY = "essay_reply_job"
REFLECTION_SAVE = "reflection_save_job"

# --- Phase 6: voice notes ---
# analyse_voice runs on the `voice` queue (one at a time: the future voice-worker serves it with
# concurrency 1); the bot defers it by name on this queue.
VOICE_QUEUE = "voice"
ANALYSE_VOICE = "analyse_voice"
CLEANUP_VOICE = "cleanup_voice_job"
