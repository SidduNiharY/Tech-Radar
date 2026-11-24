"""Procrastinate task definitions for pipeline processing and retention."""

import logging
import time
from datetime import UTC, datetime
from datetime import time as day_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from procrastinate import RetryStrategy
from procrastinate import exceptions as procrastinate_exceptions
from sqlalchemy import select

from techradar.db.engine import make_session_factory
from techradar.db.models import Answer as AnswerModel
from techradar.db.models import LibraryChapter
from techradar.exams.final30 import run_formula_sheets
from techradar.exams.sources import enqueue_sources_digest, run_suggest_topic_sources
from techradar.exams.syllabus import sync_syllabus
from techradar.library.inbox import load_limits, plan_library_intake
from techradar.library.index import index_library_chapter
from techradar.library.jobs import collect_bulk_results, plan_doc, resume_all
from techradar.library.quarantine import purge_deleted_originals
from techradar.library.summaries import summarize_doc
from techradar.llm.litellm import LiteLLMCompleter, LiteLLMEmbedder
from techradar.llm.roles import load_roles
from techradar.messaging.outbox import enqueue_message
from techradar.night.window import in_night_window, next_window_start, night_only
from techradar.ops.alerts import alert_on_failure
from techradar.ops.health import read_backup_status, run_health_checks
from techradar.ops.status import check_disk_live, check_ollama_live
from techradar.pipeline.process import PipelineDeps, collect_results, process_new_items
from techradar.pipeline.retention import cleanup_retention
from techradar.pipeline.writer import slugify
from techradar.planner.progress import run_weekly_review
from techradar.planner.sessions import close_stale_sessions, local_date
from techradar.rag.indexer import (
    IndexDeps,
    collect_clipping_results,
    plan_clipping_jobs,
    scan_vault,
    sync_index,
)
from techradar.rag.rerank import CrossEncoderReranker
from techradar.rag.retrieve import RagDeps
from techradar.settings import Settings, get_settings
from techradar.worker.app import app
from techradar.worker.ask_flow import run_ask, run_night_ask

logger = logging.getLogger(__name__)


def _get_settings() -> Settings:
    try:
        return get_settings()
    except Exception:
        return Settings(telegram_owner_chat_id=1)


def get_pipeline_deps() -> PipelineDeps:
    """Build default pipeline dependencies from system settings and local models."""
    settings = _get_settings()
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    completer = LiteLLMCompleter(roles, "http://ollama:11434")
    embedder = LiteLLMEmbedder(roles, "http://ollama:11434")
    session_factory = make_session_factory("app", settings)

    allowlist_path = Path("infra/squid/allowlist.txt")
    allowed = (
        frozenset(
            line.strip().lstrip(".")
            for line in allowlist_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
        if allowlist_path.exists()
        else frozenset()
    )

    official_path = Path("infra/sources/official_domains.txt")
    official = (
        frozenset(
            line.strip().lstrip(".")
            for line in official_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        )
        if official_path.exists()
        else frozenset()
    )

    return PipelineDeps(
        session_factory=session_factory,
        completer=completer,
        embedder=embedder,
        settings=settings,
        vault_root=settings.data_dir / "vault",
        clean_dir=settings.data_dir / "clean",
        jobs_dir=settings.data_dir / "parse-jobs",
        raw_dir=settings.data_dir / "raw",
        allowed=allowed,
        official=official,
    )


@app.task(queue="llm", lock="pipeline")
@alert_on_failure("collect_and_process")  # Phase 5
async def collect_and_process() -> None:
    """Collect parser outputs and process unindexed items."""
    deps = get_pipeline_deps()
    await collect_results(deps)
    await process_new_items(deps)


@app.task(queue="io")
@alert_on_failure("retention")  # Phase 5
async def retention() -> None:
    """Run periodic retention cleanup."""
    deps = get_pipeline_deps()
    await cleanup_retention(deps, datetime.now(UTC))


def get_index_deps() -> IndexDeps:
    """Build default RAG index dependencies from settings and embedder."""
    settings = _get_settings()
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    embedder = LiteLLMEmbedder(roles, "http://ollama:11434")
    session_factory = make_session_factory("app", settings)

    return IndexDeps(
        session_factory=session_factory,
        embedder=embedder,
        vault_root=settings.data_dir / "vault",
        library_dir=settings.data_dir / "library",
        library_inbox=settings.data_dir / "library-inbox",
        raw_dir=settings.data_dir / "raw",
        jobs_dir=settings.data_dir / "parse-jobs",
        clean_dir=settings.data_dir / "clean",
        skip=settings.index_skip,
    )


LIMITS_PATHS = (Path("/infra/intake/limits.yaml"), Path("infra/intake/limits.yaml"))


async def _queue_doc(doc_id: int) -> None:
    """Hand a freshly stored library doc to the `bulk` queue."""
    await plan_doc_job.defer_async(doc_id=doc_id)


async def intake_library(settings: Settings, deps: IndexDeps) -> list[int]:
    """Take settled files from the library and pack inboxes into the library."""
    limits_path = next((p for p in LIMITS_PATHS if p.exists()), LIMITS_PATHS[0])
    session_factory = deps.session_factory
    async with session_factory() as session:

        async def send(text: str) -> None:
            await enqueue_message(
                session,
                chat_id=settings.telegram_owner_chat_id,
                text=text,
                purpose="library_intake",
            )

        ids = await plan_library_intake(
            session,
            [(deps.library_inbox, "library"), (settings.library_packs_dir, "pack")],
            deps.library_dir,
            time.time(),
            load_limits(limits_path),
            queue_doc=_queue_doc,
            send=send,
        )
        await session.commit()
    return ids


@app.periodic(cron="*/10 * * * *")
@app.task(queue="io")
@alert_on_failure("index_sync")  # Phase 5
async def index_sync(timestamp: int | None = None) -> None:  # periodic: gets timestamp=
    """Run periodic vault and library indexing."""
    settings = _get_settings()
    deps = get_index_deps()
    try:
        await intake_library(settings, deps)
    except Exception:  # intake must never stop vault indexing
        logger.exception("library intake failed; vault indexing continues")
    scanned = scan_vault(deps.vault_root, skip=deps.skip)
    plan_clipping_jobs(deps.vault_root, scanned, deps.raw_dir, deps.jobs_dir)
    await collect_clipping_results(deps)
    await sync_index(deps)


def get_rag_deps() -> RagDeps:
    """Build default RAG dependencies for question answering."""
    settings = _get_settings()
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    completer = LiteLLMCompleter(roles, "http://ollama:11434")
    embedder = LiteLLMEmbedder(roles, "http://ollama:11434")
    ro_session_factory = make_session_factory("ro", settings)
    reranker = CrossEncoderReranker(settings.reranker_path, settings.reranker_device)

    return RagDeps(
        ro_session_factory=ro_session_factory,
        completer=completer,
        embedder=embedder,
        reranker=reranker,
        settings=settings,
    )


@app.task(queue="llm", lock="ask", name="ask")
async def ask_job(chat_id: int, question: str, doc_id: int | None = None) -> None:
    """Answer a question (of one book when doc_id is set) and enqueue the reply to the outbox.

    A hard question is deferred to `ask_night` (owner chat only); see worker/ask_flow.py.
    """
    settings = _get_settings()
    await run_ask(
        question,
        chat_id=chat_id,
        doc_id=doc_id,
        deps=get_rag_deps(),
        session_factory=make_session_factory("app", settings),
        owner_chat_id=settings.telegram_owner_chat_id,
        defer_night=_defer_ask_night,
    )


async def _defer_ask_night(question: str, doc_id: int | None) -> None:
    """Queue `ask_night` for the next night window (at once when the window is open).

    The job carries only the question and the book: the owner chat comes from settings there.
    """
    settings = _get_settings()
    start, end = (
        day_time.fromisoformat(settings.night_start),
        day_time.fromisoformat(settings.night_end),
    )
    now = datetime.now(UTC).astimezone(ZoneInfo(settings.tz))
    options: dict[str, object] = {}
    if not in_night_window(now, start, end):
        options["schedule_at"] = next_window_start(now, start)
    await ask_night.configure(**options).defer_async(question=question, doc_id=doc_id)


@app.task(queue="llm", lock="ask", name="ask_night")
@night_only(task_name="ask_night")
async def ask_night(question: str, doc_id: int | None = None) -> None:
    """Answer a deferred hard question with the night model and send it to the owner chat."""
    settings = _get_settings()
    await run_night_ask(
        question,
        doc_id=doc_id,
        deps=get_rag_deps(),
        session_factory=make_session_factory("app", settings),
        owner_chat_id=settings.telegram_owner_chat_id,
    )


@app.task(queue="llm", lock="ask", name="save_answer")
async def save_answer_job(answer_id: int) -> None:
    """Save answered Q&A to vault wiki/answers/YYYY/MM/<slug>.md and confirm via outbox."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        ans = await session.get(AnswerModel, answer_id)
        if not ans:
            return

        now = datetime.now(UTC)
        slug = slugify(ans.question[:60]) or f"answer-{answer_id}"
        rel_path = f"wiki/answers/{now.strftime('%Y/%m')}/{slug}.md"
        dest = settings.data_dir / "vault" / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        citation_paths = [
            c["doc_path"] for c in (ans.citations or []) if isinstance(c, dict) and "doc_path" in c
        ]
        fm = {
            "kind": "answer",
            "generated": True,
            "question": ans.question,
            "citations": citation_paths,
            "date": now.strftime("%Y-%m-%d"),
        }
        content = f"---\n{yaml.dump(fm, sort_keys=False)}---\n\n{ans.text}\n"
        dest.write_text(content, encoding="utf-8")

        ans.saved_path = rel_path
        await enqueue_message(
            session,
            chat_id=settings.telegram_owner_chat_id,
            text=f"Saved: {rel_path}",
            purpose="answer_saved",
            ref_id=answer_id,
        )
        await session.commit()


# --- bulk queue (Phase 2c Task 4) -------------------------------------------------
# Served by the `worker-bulk` container (`--queues=bulk`). That worker has no start hook:
# `resume_bulk_job` runs every 5 minutes and re-queues work lost to a restart, so a restarted
# worker-bulk heals itself within 5 minutes without any extra wiring. The two periodic jobs
# share one execution `lock` (they touch the same rows) and each has its own `queueing_lock`:
# while one is waiting in the queue, the next tick is skipped instead of piling up.
# worker-bulk has no network to ollama, so it never embeds: once a doc's chapters are
# committed it defers `index_library_chapters_job` on the `llm` queue (see `_queue_index`).


async def _queue_index(doc_id: int) -> None:
    """Hand a doc whose chapters were just built to the `llm` queue for indexing."""
    try:
        await index_library_chapters_job.configure(
            lock=f"index_library_{doc_id}", queueing_lock=f"index_library_{doc_id}"
        ).defer_async(doc_id=doc_id)
    except procrastinate_exceptions.AlreadyEnqueued:
        logger.info("indexing of library doc %d is already queued", doc_id)


@app.task(queue="bulk", name="plan_doc_job")
async def plan_doc_job(doc_id: int) -> None:
    """Turn one queued library doc into its first parse job (probe/full/media)."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        await plan_doc(
            session,
            doc_id,
            jobs_dir=settings.data_dir / "parse-jobs",
            library_dir=settings.data_dir / "library",
            owner_chat_id=settings.telegram_owner_chat_id,
        )  # commits the status before it writes the job file


@app.periodic(cron="* * * * *")
@app.task(
    queue="bulk",
    lock="bulk_collect",
    queueing_lock="collect_bulk_results_queued",
    name="collect_bulk_results_job",
)
@alert_on_failure("collect_bulk_results_job")  # Phase 5
async def collect_bulk_results_job(
    timestamp: int | None = None,
) -> None:  # periodic: gets timestamp=
    """Apply finished library parse results (probe, parts, whole docs)."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        counts = await collect_bulk_results(
            session,
            clean_dir=settings.data_dir / "clean",
            jobs_dir=settings.data_dir / "parse-jobs",
            library_dir=settings.data_dir / "library",
            part_pages=settings.library_part_pages,
            owner_chat_id=settings.telegram_owner_chat_id,
            on_chapters_ready=_queue_index,
        )
    if counts["handled"] or counts["errors"]:
        logger.info("bulk results handled: %s", counts)


@app.periodic(cron="*/5 * * * *")
@app.task(
    queue="bulk",
    lock="bulk_collect",
    queueing_lock="resume_bulk_queued",
    name="resume_bulk_job",
)
@alert_on_failure("resume_bulk_job")  # Phase 5
async def resume_bulk_job(timestamp: int | None = None) -> None:  # periodic: gets timestamp=
    """Re-queue lost parse jobs of every stuck library doc (queued or processing).

    Also deletes the originals of held docs the owner deleted with /quarantine: the bot has
    no library mount, so this worker (rw on /data/library) does it.
    """
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        resumed = await resume_all(
            session,
            jobs_dir=settings.data_dir / "parse-jobs",
            library_dir=settings.data_dir / "library",
            clean_dir=settings.data_dir / "clean",
            part_pages=settings.library_part_pages,
            owner_chat_id=settings.telegram_owner_chat_id,
            on_chapters_ready=_queue_index,
        )  # commits per doc
        purged = await purge_deleted_originals(session, library_dir=settings.data_dir / "library")
    if purged:
        logger.info("deleted %d originals of deleted held library docs", purged)
    if any(resumed.values()):
        logger.info("bulk resume re-queued parts: %s", resumed)


# --- indexing (Phase 2c Task 6 wiring) ---------------------------------------------
# Queue `llm`: it needs the embedder on ollama. One run per doc (lock and queueing lock are
# set when `_queue_index` defers it). After the chapters are indexed it defers the summaries,
# which send the owner's "Ready" message; this job tells the owner nothing.


@app.task(
    queue="llm",
    name="index_library_chapters_job",
    retry=RetryStrategy(max_attempts=4, wait=300),  # an embedder outage is retried, not lost
)
async def index_library_chapters_job(doc_id: int) -> None:
    """Index every chapter of a doc into `chunks`, then queue its summaries."""
    deps = get_index_deps()
    async with deps.session_factory() as session:
        chapter_ids = (
            (
                await session.execute(
                    select(LibraryChapter.id)
                    .where(LibraryChapter.doc_id == doc_id)
                    .order_by(LibraryChapter.ordinal)
                )
            )
            .scalars()
            .all()
        )
    indexed = 0
    for chapter_id in chapter_ids:
        n = await index_library_chapter(deps, chapter_id)
        if n == 0:
            logger.warning("library doc %d chapter %d indexed 0 chunks", doc_id, chapter_id)
        indexed += n
    logger.info(
        "indexed library doc %d: %d chunks in %d chapters", doc_id, indexed, len(chapter_ids)
    )
    await _queue_summaries(doc_id)


# --- summaries (Phase 2c Task 7) ---------------------------------------------------
# One run per doc, not one for all books: the lock and the queueing lock are `summ:<doc id>`,
# set when the job is deferred (`_queue_summaries`, also used by the night deferral below), so
# a long book no longer holds every other book back and duplicates for one doc never pile up.
# The job works only inside the night window: it asks before each chapter, and when the window
# closes (or a chapter failed and is due another try) it queues itself for the next window.


async def _queue_summaries(doc_id: int, *, when: datetime | None = None) -> None:
    """Defer the summarize job for one doc, with its own lock; `when` is the earliest start."""
    options: dict[str, object] = {"lock": f"summ:{doc_id}", "queueing_lock": f"summ:{doc_id}"}
    if when is not None:
        options["schedule_at"] = when
    try:
        await summarize_chapters_job.configure(**options).defer_async(doc_id=doc_id)
    except procrastinate_exceptions.AlreadyEnqueued:
        logger.info("summaries of library doc %d are already queued", doc_id)


async def _defer_summaries(when: datetime, kwargs: dict[str, Any]) -> None:
    """`night_only`'s deferral outside the window: same job, same arguments, per-doc locks."""
    await _queue_summaries(int(kwargs["doc_id"]), when=when)


@app.task(queue="llm", name="summarize_chapters_job")
@night_only(task_name="summarize_chapters_job", defer=_defer_summaries)
async def summarize_chapters_job(doc_id: int) -> None:
    """Summarise a doc's chapters into the vault, then make it ready (night window only)."""
    settings = _get_settings()
    start, end = (
        day_time.fromisoformat(settings.night_start),
        day_time.fromisoformat(settings.night_end),
    )
    zone = ZoneInfo(settings.tz)

    def in_window() -> bool:
        return in_night_window(datetime.now(UTC).astimezone(zone), start, end)

    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    completer = LiteLLMCompleter(roles, "http://ollama:11434")
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        counts = await summarize_doc(
            session,
            completer,
            doc_id,
            vault_root=settings.data_dir / "vault",
            library_dir=settings.data_dir / "library",
            owner_chat_id=settings.telegram_owner_chat_id,
            in_window=in_window,
        )
    logger.info("summaries for doc %d: %s", doc_id, counts)
    if counts.get("more"):
        # the window closed, or a chapter failed and gets another try: next window start
        await _queue_summaries(
            doc_id, when=next_window_start(datetime.now(UTC).astimezone(zone), start)
        )


# --- Phase 5 ---------------------------------------------------------------------
# Planner, progress and reliability. Jobs never fall back to the Mac (D19): when the server
# is off they wait, and the next tick catches up once. Every body below is idempotent.


@app.periodic(cron="0 * * * *")
@app.task(
    queue="io",
    lock="close_stale_sessions",
    queueing_lock="close_stale_sessions_queued",
    name="close_stale_sessions_job",
)
@alert_on_failure("close_stale_sessions_job")
async def close_stale_sessions_job(
    timestamp: int | None = None,
) -> None:  # periodic: gets timestamp=
    """Close study sessions left running for more than 4 hours (the owner forgot /stop)."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        closed = await close_stale_sessions(session, datetime.now(UTC))
        await session.commit()
    if closed:
        logger.info("auto-closed %d stale study sessions", closed)


# Sundays at 19:00 India time. Procrastinate reads cron in UTC: 13:30 UTC is 19:00 IST.
# A missed Sunday is not repeated later (one review per week, see `run_weekly_review`).
@app.periodic(cron="30 13 * * 0")
@app.task(
    queue="io",
    lock="weekly_review",
    queueing_lock="weekly_review_queued",
    name="weekly_review_job",
)
@alert_on_failure("weekly_review_job")
async def weekly_review_job(timestamp: int | None = None) -> None:  # periodic: gets timestamp=
    """Write this week's review page into the vault and send the owner a summary."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        await run_weekly_review(
            session,
            local_date(datetime.now(UTC)),
            owner_chat_id=settings.telegram_owner_chat_id,
            vault_root=settings.data_dir / "vault",
        )
        await session.commit()


# Hourly. Reads the backup status file the backup script writes into `data/status/` (the
# worker needs `./data/status` mounted read-only: compose.yaml, left for the owner). A missing
# file counts as "backup has not succeeded", so the alert also tells the owner the mount is
# missing. Alerts are de-duplicated per problem for 6 hours, so downtime sends nothing twice.
@app.periodic(cron="5 * * * *")
@app.task(
    queue="io",
    lock="health",
    queueing_lock="health_queued",
    name="health_job",
)
@alert_on_failure("health_job")
async def health_job(timestamp: int | None = None) -> None:  # periodic: gets timestamp=
    """Check disk, fetching, backup and Ollama; alert the owner about each problem."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    ollama_ok = await check_ollama_live() is not None
    async with session_factory() as session:
        await run_health_checks(
            session,
            now=datetime.now(UTC),
            owner_chat_id=settings.telegram_owner_chat_id,
            disk_free_pct=check_disk_live(settings.data_dir),
            ollama_ok=ollama_ok,
            backup_status=read_backup_status(settings.data_dir / "status" / "backup.json"),
        )
        await session.commit()


# --- Phase 8: exams ---------------------------------------------------------------
# Jobs of the exam tools (plans/2026-11-07-techradar-phase8-exams.md). Each one opens its own
# session; the exams modules take the session and the time and never open one themselves.


@app.periodic(cron="30 3 * * *")
@app.task(queue="io", queueing_lock="syllabus_sync_queued", name="syllabus_sync_job")
async def syllabus_sync_job(timestamp: int | None = None) -> None:
    """Daily: read `syllabus/**/*.md` from the vault into `syllabus_topics` (Task 1).

    A periodic job is always called with `timestamp=` (procrastinate adds it), so every
    periodic job of this block takes it.
    """
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        topics = await sync_syllabus(session, settings.data_dir / "vault")
        await session.commit()
    logger.info("syllabus sync: %d topics", topics)


def _exam_models() -> tuple[LiteLLMCompleter, LiteLLMEmbedder]:
    """The local worker/checker models and the embedder (never a cloud model)."""
    roles = load_roles(Path("infra/models/roles.yaml"), allow_cloud=False)
    return LiteLLMCompleter(roles, "http://ollama:11434"), LiteLLMEmbedder(
        roles, "http://ollama:11434"
    )


# Nightly at 20:00 UTC = 01:30 in Asia/Kolkata, inside the night window (01:00-05:00); outside
# it `night_only` queues the job for the next window start instead of running it.
@app.periodic(cron="0 20 * * *")
@app.task(queue="llm", queueing_lock="suggest_sources_queued", name="suggest_topic_sources_job")
@night_only(task_name="suggest_topic_sources_job")
async def suggest_topic_sources_job(timestamp: int | None = None) -> None:
    """Nightly: pick syllabus topics for unlinked library chapters (Task 2b).

    A past-paper tag the owner already confirmed links at once; a model's chapter pick stays
    `suggested` until the owner presses Keep in the Sunday digest (`srcok:<id>`).
    """
    settings = _get_settings()
    completer, embedder = _exam_models()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        created = await run_suggest_topic_sources(
            session,
            embedder,
            completer,
            now=datetime.now(UTC),
            vault_root=settings.data_dir / "vault",
        )
        await session.commit()
    logger.info("topic sources: %d new", created)


# Sundays 12:45 UTC = 18:15 in Asia/Kolkata.
@app.periodic(cron="45 12 * * 0")
@app.task(queue="io", queueing_lock="sources_digest_queued", name="sources_digest_job")
async def sources_digest_job(timestamp: int | None = None) -> None:
    """Sundays 18:15: ask the owner to confirm up to 10 suggested sources (Task 2b)."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        sent = await enqueue_sources_digest(session, settings.telegram_owner_chat_id)
        await session.commit()
    logger.info("sources digest: %d suggestions queued", sent)


# Nightly at 20:30 UTC = 02:00 in Asia/Kolkata, inside the night window.
@app.periodic(cron="30 20 * * *")
@app.task(queue="llm", queueing_lock="formula_sheets_queued", name="formula_sheets_job")
@night_only(task_name="formula_sheets_job")
async def formula_sheets_job(timestamp: int | None = None) -> None:
    """Night: in the final 30 days of an exam, write a cited formula sheet per syllabus
    subject from the owner's own notes (Task 7). Does nothing without an exam date set.
    """
    settings = _get_settings()
    today = datetime.now(UTC).astimezone(ZoneInfo(settings.tz)).date()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        counts = await run_formula_sheets(
            session, get_rag_deps(), settings.data_dir / "vault", today
        )
    logger.info("formula sheets: %s", counts)
