"""Procrastinate task definitions for pipeline processing and retention."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from techradar.bot.render import render_answer
from techradar.db.engine import make_session_factory
from techradar.db.models import Answer as AnswerModel
from techradar.library.inbox import load_limits, plan_library_intake
from techradar.library.jobs import collect_bulk_results, plan_doc, resume_all
from techradar.llm.litellm import LiteLLMCompleter, LiteLLMEmbedder
from techradar.llm.roles import load_roles
from techradar.messaging.outbox import Button, enqueue_message
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
    await intake_library(settings, deps)
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
# worker-bulk heals itself within 5 minutes without any extra wiring.


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
        )
        await session.commit()


@app.periodic(cron="* * * * *")
@app.task(queue="bulk", lock="bulk_collect", name="collect_bulk_results_job")
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
        )
    if counts["handled"]:
        logger.info("bulk results handled: %s", counts)


@app.periodic(cron="*/5 * * * *")
@app.task(queue="bulk", lock="bulk_collect", name="resume_bulk_job")
async def resume_bulk_job() -> None:
    """Re-queue lost parse jobs of every `processing` library doc."""
    settings = _get_settings()
    session_factory = make_session_factory("app", settings)
    async with session_factory() as session:
        resumed = await resume_all(
            session,
            jobs_dir=settings.data_dir / "parse-jobs",
            library_dir=settings.data_dir / "library",
            clean_dir=settings.data_dir / "clean",
        )
        await session.commit()
    if any(resumed.values()):
        logger.info("bulk resume re-queued parts: %s", resumed)
