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

# The queue of every night-window job (Phase 7 Task 1). One worker serves it with concurrency 1,
# so two heavy night jobs never share the GPU.
NIGHT_QUEUE = "night"

# --- Phase 7 ---
PREDICTIONS_SYNC = "predictions_sync_job"
