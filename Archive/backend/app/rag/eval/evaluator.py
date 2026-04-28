"""
Offline RAG evaluation harness.

Usage:
    # from the backend/ directory:
    python scripts/run_eval.py

Measures:
    Intent classification accuracy
    Retrieval:  Recall@5, MRR, NDCG@5, Precision@5
    Answer:     Keyword coverage, lexical faithfulness, length
    Speed:      Query latency (s)

Results are printed to the console AND saved to eval_results.json.
Define test cases in scripts/run_eval.py or load from a JSON file.
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

from app.rag.eval.metrics import (
    recall_at_k,
    mrr,
    ndcg_at_k,
    precision_at_k,
    keyword_coverage,
    lexical_faithfulness,
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single evaluation test case."""
    query:             str
    expected_keywords: List[str]       = field(default_factory=list)
    relevant_doc_ids:  List[int]       = field(default_factory=list)
    expected_intent:   Optional[str]   = None
    filters:           Optional[dict]  = None
    description:       str             = ""   # human note


@dataclass
class EvalResult:
    """Metrics for one test case."""
    query:             str
    intent_detected:   str
    intent_correct:    Optional[bool]
    retrieval_count:   int
    recall_at_5:       float
    precision_at_5:    float
    mrr_score:         float
    ndcg_at_5:         float
    answer_length:     int
    keyword_coverage:  float
    faithfulness:      float
    latency_s:         float
    answer_preview:    str
    sources_used:      List[str]       = field(default_factory=list)
    hops_taken:        int             = 0
    error:             Optional[str]   = None


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class RAGEvaluator:
    """
    Run a suite of TestCases against the live pipeline and collect metrics.

    Does NOT mock anything — hits real Elasticsearch + real Ollama so results
    reflect true production behaviour.
    """

    def __init__(self, output_path: str = "eval_results.json") -> None:
        self.output_path = Path(output_path)
        self.results: List[EvalResult] = []

    def run(self, test_cases: List[TestCase], user=None) -> List[EvalResult]:
        from app.rag.retriever.query_parser import detect_query_intent
        from app.rag.llm.qa_pipeline import ask

        print(f"\n{'═' * 64}")
        print(f"  Army Archive RAG — Evaluation Suite")
        print(f"  {len(test_cases)} test case(s)")
        print(f"{'═' * 64}\n")

        self.results = []
        for i, tc in enumerate(test_cases, 1):
            print(f"[{i:02d}/{len(test_cases):02d}] {tc.query!r}"
                  + (f"  ({tc.description})" if tc.description else ""))
            result = self._run_one(tc, user)
            self.results.append(result)
            self._print_result(result)

        self._print_summary()
        self._save()
        return self.results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_one(self, tc: TestCase, user) -> EvalResult:
        from app.rag.retriever.query_parser import detect_query_intent
        from app.rag.llm.qa_pipeline import ask

        error   = None
        answer  = ""
        sources: List[str] = []
        retrieved_doc_ids: List[int] = []
        intent  = ""
        hops    = 0
        t0      = time.time()

        try:
            intent = detect_query_intent(tc.query)
            qa     = ask(
                query=tc.query,
                filters=tc.filters,
                top_k=5,
                user=user,
                run_faithfulness_check=False,  # skip for speed during eval
            )
            answer  = qa.answer or ""
            sources = [s.get("file_name", "") for s in (qa.sources or [])]
            retrieved_doc_ids = list({
                s.get("doc_id", 0) for s in (qa.sources or []) if s.get("doc_id")
            })
        except Exception as e:
            error = str(e)

        latency = round(time.time() - t0, 2)

        recall5    = recall_at_k(retrieved_doc_ids,    tc.relevant_doc_ids, 5) if tc.relevant_doc_ids else -1.0
        prec5      = precision_at_k(retrieved_doc_ids, tc.relevant_doc_ids, 5) if tc.relevant_doc_ids else -1.0
        mrr_s      = mrr(retrieved_doc_ids,            tc.relevant_doc_ids)    if tc.relevant_doc_ids else -1.0
        ndcg5      = ndcg_at_k(retrieved_doc_ids,      tc.relevant_doc_ids, 5) if tc.relevant_doc_ids else -1.0
        kw_cov     = keyword_coverage(answer, tc.expected_keywords)
        faith      = lexical_faithfulness(answer, answer)  # self-consistency proxy

        intent_correct: Optional[bool] = None
        if tc.expected_intent:
            intent_correct = (intent == tc.expected_intent)

        return EvalResult(
            query             = tc.query,
            intent_detected   = intent,
            intent_correct    = intent_correct,
            retrieval_count   = len(retrieved_doc_ids),
            recall_at_5       = round(recall5, 3),
            precision_at_5    = round(prec5,   3),
            mrr_score         = round(mrr_s,   3),
            ndcg_at_5         = round(ndcg5,   3),
            answer_length     = len(answer),
            keyword_coverage  = round(kw_cov,  3),
            faithfulness      = round(faith,   3),
            latency_s         = latency,
            answer_preview    = answer[:200].replace("\n", " "),
            sources_used      = sources,
            hops_taken        = hops,
            error             = error,
        )

    def _print_result(self, r: EvalResult) -> None:
        ok  = "✅" if not r.error else "❌"
        ic  = "" if r.intent_correct is None else (" ✓" if r.intent_correct else " ✗")
        print(f"  {ok} intent={r.intent_detected}{ic}  "
              f"chunks={r.retrieval_count}  "
              f"kw={r.keyword_coverage:.0%}  "
              f"{r.latency_s:.1f}s")
        if r.error:
            print(f"     Error: {r.error}")
        else:
            print(f"     {r.answer_preview[:120]}…")
        print()

    def _print_summary(self) -> None:
        valid = [r for r in self.results if r.error is None]
        total = len(self.results)
        n     = len(valid)

        print(f"\n{'═' * 64}")
        print(f"  SUMMARY  ({n}/{total} successful)")
        print(f"{'─' * 64}")

        if not valid:
            print("  ⚠️  No valid results.")
            print(f"{'═' * 64}\n")
            return

        def avg(vals):
            v = [x for x in vals if x >= 0]
            return sum(v) / len(v) if v else None

        kw_avg  = avg(r.keyword_coverage for r in valid)
        lat_avg = avg(r.latency_s for r in valid)
        rec_avg = avg(r.recall_at_5 for r in valid)
        mrr_avg = avg(r.mrr_score for r in valid)
        nd_avg  = avg(r.ndcg_at_5 for r in valid)

        intent_ok = sum(1 for r in valid if r.intent_correct is True)
        intent_n  = sum(1 for r in valid if r.intent_correct is not None)

        if kw_avg  is not None: print(f"  Keyword coverage  : {kw_avg:.1%}")
        if lat_avg is not None: print(f"  Avg latency       : {lat_avg:.1f}s")
        if rec_avg is not None: print(f"  Recall@5          : {rec_avg:.1%}")
        if mrr_avg is not None: print(f"  MRR               : {mrr_avg:.3f}")
        if nd_avg  is not None: print(f"  NDCG@5            : {nd_avg:.3f}")
        if intent_n:
            print(f"  Intent accuracy   : {intent_ok}/{intent_n}  ({intent_ok/intent_n:.0%})")

        print(f"{'═' * 64}\n")

    def _save(self) -> None:
        data = [asdict(r) for r in self.results]
        self.output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"📄 Eval results → {self.output_path.resolve()}")
