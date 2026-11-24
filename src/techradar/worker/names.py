"""Task names for background worker jobs."""

ASK = "ask"
SAVE_ANSWER = "save_answer"

# The queue of every night-window job (Phase 7 Task 1). One worker serves it with concurrency 1,
# so two heavy night jobs never share the GPU.
NIGHT_QUEUE = "night"

# --- Phase 7 ---
PREDICTIONS_SYNC = "predictions_sync_job"
