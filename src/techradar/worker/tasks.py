"""Procrastinate task definitions for pipeline processing and retention."""

from datetime import UTC, datetime
from pathlib import Path

from techradar.db.engine import make_session_factory
from techradar.llm.litellm import LiteLLMCompleter, LiteLLMEmbedder
from techradar.llm.roles import load_roles
from techradar.pipeline.process import PipelineDeps, collect_results, process_new_items
from techradar.pipeline.retention import cleanup_retention
from techradar.rag.indexer import (
    IndexDeps,
    collect_clipping_results,
    collect_library_results,
    plan_clipping_jobs,
    plan_library_jobs,
    scan_vault,
    sync_index,
)
from techradar.settings import settings
from techradar.worker.app import app


def get_pipeline_deps() -> PipelineDeps:
    """Build default pipeline dependencies from system settings and local models."""
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


@app.periodic(cron="*/10 * * * *")
@app.task(queue="io")
async def index_sync() -> None:
    """Run periodic vault and library indexing."""
    deps = get_index_deps()
    plan_library_jobs(
        deps.library_inbox,
        settings.data_dir / "library" / "originals",
        deps.jobs_dir,
    )
    await collect_library_results(deps)
    scanned = scan_vault(deps.vault_root, skip=deps.skip)
    plan_clipping_jobs(deps.vault_root, scanned, deps.raw_dir, deps.jobs_dir)
    await collect_clipping_results(deps)
    await sync_index(deps)
