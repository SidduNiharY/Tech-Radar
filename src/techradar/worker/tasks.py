"""Procrastinate task definitions for pipeline processing and retention."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from procrastinate import RetryStrategy
from procrastinate import exceptions as procrastinate_exceptions
from sqlalchemy import select

from techradar.bot.render import render_answer
from techradar.db.engine import make_session_factory
from techradar.db.models import Answer as AnswerModel
from techradar.db.models import LibraryChapter
from techradar.library.inbox import load_limits, plan_library_intake
from techradar.library.index import index_library_chapter
from techradar.library.jobs import collect_bulk_results, plan_doc, resume_all
from techradar.library.summaries import summarize_doc
from techradar.llm.litellm import LiteLLMCompleter, LiteLLMEmbedder
from techradar.llm.roles import load_roles
from techradar.messaging.outbox import Button, enqueue_message
from techradar.night.window import night_only
from techradar.pipeline.process import PipelineDeps, collect_results, process_new_items
from techradar.pipeline.retention import cleanup_retention
from techradar.pipeline.writer import slugify
from techradar.rag.answer import answer_question
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
async def collect_and_process() -> None:
    """Collect parser outputs and process unindexed items."""
    deps = get_pipeline_deps()
    await collect_results(deps)
    await process_new_items(deps)


@app.task(queue="io")
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
async def index_sync() -> None:
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
async def ask_job(chat_id: int, question: str) -> None:
    """Answer question using grounded RAG and enqueue response to outbox."""
    settings = _get_settings()
    deps = get_rag_deps()
    answer = await answer_question(question, deps)

    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        ans_row = AnswerModel(
            chat_id=chat_id,
            question=question,
            text=answer.text,
            citations=[c.model_dump() for c in answer.citations],
            status=answer.status,
            used_unverified=answer.used_unverified,
            flags=answer.flags,
        )
        session.add(ans_row)
        await session.flush()

        buttons = None
        if answer.status == "answered":
            buttons = [[Button(text="Save to vault", data=f"save_answer:{ans_row.id}")]]

        rendered = render_answer(answer)
        await enqueue_message(
            session,
            chat_id=chat_id,
            text=rendered,
            purpose="answer",
            buttons=buttons,
            ref_id=ans_row.id,
        )
        await session.commit()


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
async def collect_bulk_results_job() -> None:
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
async def resume_bulk_job() -> None:
    """Re-queue lost parse jobs of every stuck library doc (queued or processing)."""
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
    await summarize_chapters_job.defer_async(doc_id=doc_id)


# --- summaries (Phase 2c Task 7) ---------------------------------------------------
# One lock for all summary jobs: the lock is fixed when the task is declared, so it also
# holds when `night_only` re-defers a job to the next window. It keeps two runs for the same
# doc from overlapping (and the single local GPU model busy with one book at a time).


@app.task(queue="llm", lock="summarize", name="summarize_chapters_job")
@night_only(task_name="summarize_chapters_job")
async def summarize_chapters_job(doc_id: int) -> None:
    """Summarise a doc's chapters into the vault, then make it ready (night window only)."""
    settings = _get_settings()
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
        )
    logger.info("summaries for doc %d: %s", doc_id, counts)
