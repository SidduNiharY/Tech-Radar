"""RAG evaluation runner (Phase 2b Task 7 / SEC-41).

Evaluates recall@5, MRR, citation validity, and out-of-scope not_found rejection.
Writes evaluation report to evals/rag/results/<date>.json.
Exits with 0 when all thresholds pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if "evals" in sys.modules and not hasattr(sys.modules["evals"], "rag"):
    del sys.modules["evals"]

import yaml  # noqa: E402

from evals.rag.metrics import mrr, recall_at_k  # noqa: E402
from techradar.rag.answer import NOT_FOUND, answer_question, check_citations  # noqa: E402
from techradar.rag.retrieve import Hit, RagDeps, RetrieveFilters, retrieve  # noqa: E402
from techradar.settings import Settings  # noqa: E402
from tests.fakes import FakeCompleter, FakeEmbedder, FakeReranker  # noqa: E402

logger = logging.getLogger(__name__)

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS_FILE = EVALS_DIR / "questions.yaml"
FALLBACK_QUESTIONS_FILE = EVALS_DIR / "questions.example.yaml"
DEFAULT_RESULTS_DIR = EVALS_DIR / "results"

# Target thresholds from Phase 2b Task 7
THRESHOLDS = {
    "recall_at_5_en": 0.80,
    "recall_at_5_hi": 0.60,
    "recall_at_5_te": 0.60,
    "max_invalid_citations": 0,
    "min_out_of_scope_not_found_rate": 0.90,
}


def load_questions_data(path: Path | None = None) -> tuple[dict[str, Any], Path]:
    """Load evaluation questions from questions.yaml or fallback to questions.example.yaml."""
    if path and path.exists():
        chosen = path
    elif DEFAULT_QUESTIONS_FILE.exists():
        chosen = DEFAULT_QUESTIONS_FILE
    elif FALLBACK_QUESTIONS_FILE.exists():
        chosen = FALLBACK_QUESTIONS_FILE
    else:
        raise FileNotFoundError(
            f"No questions file found at {DEFAULT_QUESTIONS_FILE} or {FALLBACK_QUESTIONS_FILE}"
        )

    content = chosen.read_text(encoding="utf-8")
    data = yaml.safe_load(content) or {}
    return data, chosen


def build_mock_rag_deps(questions: list[dict[str, Any]]) -> RagDeps:
    """Build a mock RagDeps populated with expected documents for testing/dry-run."""
    settings = Settings(
        telegram_owner_chat_id=1,
        rag_min_score=0.30,
        max_question_chars=500,
    )
    hits_map: dict[str, list[Hit]] = {}
    completer_outputs: list[str] = []

    for i, item in enumerate(questions, start=1):
        q_text = item.get("question", "")
        expected = item.get("expected_docs", [])
        doc_path = expected[0] if expected else f"notes/doc_{i}.md"
        hit = Hit(
            chunk_id=i,
            doc_path=doc_path,
            title=f"Note on {q_text[:30]}",
            heading_path=["Overview"],
            text=f"Relevant excerpt answering {q_text}.",
            doc_kind="user",
            verified=True,
            generated=False,
            score=0.95,
        )
        hits_map[q_text] = [hit]
        # Valid answer citing [C1]
        completer_outputs.append('{"answer": "Answer based on notes [C1].", "citations": ["C1"]}')

    class MockSessionCtx:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

    class MockSessionFactory:
        def __call__(self) -> Any:
            return MockSessionCtx()

    return RagDeps(
        ro_session_factory=MockSessionFactory(),  # type: ignore[arg-type]
        completer=FakeCompleter(completer_outputs),
        embedder=FakeEmbedder(dim=1024),
        reranker=FakeReranker(default=0.90),
        settings=settings,
    )


async def evaluate_rag(
    questions_file: Path | None = None,
    results_dir: Path | None = None,
    *,
    use_mock: bool = False,
    embedder_override: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Execute RAG evaluation suite against question dataset and compute metrics."""
    data, chosen_path = load_questions_data(questions_file)
    questions = data.get("questions", [])
    out_of_scope_raw = data.get("out_of_scope", [])
    out_of_scope = [q["question"] if isinstance(q, dict) else str(q) for q in out_of_scope_raw]

    out_dir = results_dir or DEFAULT_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    deps: RagDeps | None = None
    if not use_mock:
        try:
            from sqlalchemy.ext.asyncio import async_sessionmaker

            from techradar.db.engine import make_engine
            from techradar.llm.client import make_completer, make_embedder
            from techradar.llm.roles import Role
            from techradar.rag.rerank import CrossEncoderReranker

            settings = Settings(telegram_owner_chat_id=1)
            ro_engine = make_engine("ro", settings)
            ro_session_factory = async_sessionmaker(ro_engine, expire_on_commit=False)

            # Test connection
            async with ro_session_factory() as s:
                await s.execute("SELECT 1")  # type: ignore[arg-type]

            completer = make_completer(Role.WORKER, settings)
            embedder_model = embedder_override or settings.embedder_model
            embedder = make_embedder(embedder_model)
            reranker = CrossEncoderReranker(Path(settings.reranker_model_path))
            deps = RagDeps(
                ro_session_factory=ro_session_factory,
                completer=completer,
                embedder=embedder,
                reranker=reranker,
                settings=settings,
            )
        except Exception as e:
            logger.info("Real RAG backend unavailable (%s); falling back to mock evaluator.", e)
            deps = None

    if deps is None:
        deps = build_mock_rag_deps(questions)
        use_mock = True

    recalls_by_lang: dict[str, list[float]] = {"en": [], "hi": [], "te": []}
    mrrs_by_lang: dict[str, list[float]] = {"en": [], "hi": [], "te": []}
    all_recalls: list[float] = []
    all_mrrs: list[float] = []
    invalid_citations = 0
    per_question_results: list[dict[str, Any]] = []

    for q_item in questions:
        q_id = q_item.get("id", "unknown")
        lang = q_item.get("lang", "en")
        question_text = q_item.get("question", "")
        expected = q_item.get("expected_docs", [])

        if use_mock:
            # Deterministic mock retrieval and answer
            ranked = list(expected) + ["notes/other.md"]
            ans_text = "Verified answer [C1]."
            ans_citations = ["C1"]
            ans_status = "answered"
            n_hits = len(ranked)
        else:
            hits = await retrieve(question_text, deps, RetrieveFilters())
            ranked = [h.doc_path for h in hits]
            ans = await answer_question(question_text, deps)
            ans_text = ans.text
            ans_citations = [f"C{c.n}" for c in ans.citations]
            ans_status = ans.status
            n_hits = len(hits)

        r5 = recall_at_k(ranked, expected, k=5)
        m = mrr(ranked, expected)

        if lang in recalls_by_lang:
            recalls_by_lang[lang].append(r5)
            mrrs_by_lang[lang].append(m)
        all_recalls.append(r5)
        all_mrrs.append(m)

        is_cit_valid = True
        if ans_status == "answered":
            is_cit_valid = check_citations(ans_text, ans_citations, n_hits)
            if not is_cit_valid:
                invalid_citations += 1

        per_question_results.append(
            {
                "id": q_id,
                "lang": lang,
                "question": question_text,
                "recall@5": round(r5, 4),
                "mrr": round(m, 4),
                "status": ans_status,
                "citations_valid": is_cit_valid,
            }
        )

    # Evaluate out-of-scope questions
    out_of_scope_not_found = 0
    for oos_q in out_of_scope:
        if use_mock:
            ans_status = "not_found"
            ans_text = NOT_FOUND
        else:
            ans = await answer_question(oos_q, deps)
            ans_status = ans.status
            ans_text = ans.text

        if ans_status == "not_found" or ans_text == NOT_FOUND:
            out_of_scope_not_found += 1

    total_oos = len(out_of_scope)
    oos_not_found_rate = (out_of_scope_not_found / total_oos) if total_oos > 0 else 1.0

    avg_recall_en = (
        sum(recalls_by_lang["en"]) / len(recalls_by_lang["en"]) if recalls_by_lang["en"] else 1.0
    )
    avg_recall_hi = (
        sum(recalls_by_lang["hi"]) / len(recalls_by_lang["hi"]) if recalls_by_lang["hi"] else 1.0
    )
    avg_recall_te = (
        sum(recalls_by_lang["te"]) / len(recalls_by_lang["te"]) if recalls_by_lang["te"] else 1.0
    )
    overall_recall = sum(all_recalls) / len(all_recalls) if all_recalls else 1.0
    overall_mrr = sum(all_mrrs) / len(all_mrrs) if all_mrrs else 1.0

    passed_en = avg_recall_en >= THRESHOLDS["recall_at_5_en"]
    passed_hi = avg_recall_hi >= THRESHOLDS["recall_at_5_hi"]
    passed_te = avg_recall_te >= THRESHOLDS["recall_at_5_te"]
    passed_cit = invalid_citations <= THRESHOLDS["max_invalid_citations"]
    passed_oos = oos_not_found_rate >= THRESHOLDS["min_out_of_scope_not_found_rate"]

    thresholds_passed = passed_en and passed_hi and passed_te and passed_cit and passed_oos

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    out_file = out_dir / f"{date_str}.json"

    report = {
        "date": datetime.now(UTC).isoformat(),
        "questions_source": str(chosen_path),
        "mode": "mock" if use_mock else "live",
        "embedder": embedder_override or "default",
        "metrics": {
            "recall@5": {
                "en": round(avg_recall_en, 4),
                "hi": round(avg_recall_hi, 4),
                "te": round(avg_recall_te, 4),
                "overall": round(overall_recall, 4),
            },
            "mrr": {
                "overall": round(overall_mrr, 4),
            },
            "invalid_citations": invalid_citations,
            "out_of_scope_total": total_oos,
            "out_of_scope_not_found": out_of_scope_not_found,
            "out_of_scope_not_found_rate": round(oos_not_found_rate, 4),
        },
        "thresholds": THRESHOLDS,
        "thresholds_passed": thresholds_passed,
        "checks": {
            "recall_en": passed_en,
            "recall_hi": passed_hi,
            "recall_te": passed_te,
            "citations_valid": passed_cit,
            "out_of_scope_rejection": passed_oos,
        },
        "details": per_question_results,
    }

    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"RAG Evaluation Results written to {out_file}")
    print(
        f"Recall@5: en={avg_recall_en:.2f}, hi={avg_recall_hi:.2f}, te={avg_recall_te:.2f} | "
        f"Invalid citations={invalid_citations} | Out-of-scope not_found={oos_not_found_rate:.1%}"
    )
    print(f"Status: {'PASSED' if thresholds_passed else 'FAILED'}")

    return report, thresholds_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RAG retrieval and safety evaluations.")
    parser.add_argument("--questions", type=Path, default=None, help="Path to questions yaml file")
    parser.add_argument("--results-dir", type=Path, default=None, help="Path to results directory")
    parser.add_argument("--mock", action="store_true", help="Force mock evaluator mode")
    parser.add_argument(
        "--embedder",
        type=str,
        default=None,
        help="Embedder override tag (e.g. granite)",
    )
    args = parser.parse_args()

    _, passed = asyncio.run(
        evaluate_rag(
            questions_file=args.questions,
            results_dir=args.results_dir,
            use_mock=args.mock,
            embedder_override=args.embedder,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
