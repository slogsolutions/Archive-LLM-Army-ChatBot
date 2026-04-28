"""
RAG Evaluation Script — Recall@k, Precision@k, MRR, NDCG@k
============================================================

Usage
-----
# Run against queries.json with k=5
python scripts/evaluate_rag.py --queries scripts/eval_queries.json --k 5

# Generate a sample queries file to annotate
python scripts/evaluate_rag.py --generate-template --out scripts/eval_queries.json

# Reduce cost: retrieval only (no LLM), much faster evaluation
python scripts/evaluate_rag.py --queries scripts/eval_queries.json --retrieval-only

Query file format (JSON array)
-------------------------------
[
  {
    "query": "What is Bluetooth?",
    "relevant_doc_ids": [9, 10],        // IDs of documents that SHOULD be retrieved
    "relevant_keywords": ["bluetooth",  // proxy: if these words appear in retrieved
                          "wireless",   //   chunks → treat as relevant (no labels needed)
                          "UHF"]
  },
  ...
]

If "relevant_doc_ids" is empty / absent, the script falls back to keyword-based
relevance: a retrieved chunk is "relevant" if it contains any of the
"relevant_keywords".  This lets you evaluate without hand-labelling every chunk.

Metrics
-------
Recall@k     — fraction of relevant docs appearing in top-k results
Precision@k  — fraction of top-k results that are relevant
MRR          — mean reciprocal rank of the first relevant result
NDCG@k       — normalised discounted cumulative gain (rank-weighted)
Latency      — retrieval latency in seconds (embedding + ES search)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

# ── path setup ────────────────────────────────────────────────────────────────
# Allow running from project root: python scripts/evaluate_rag.py
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend)

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def recall_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    if not relevant_ids:
        return -1.0
    hits = sum(1 for rid in retrieved_ids[:k] if rid in relevant_ids)
    return hits / len(relevant_ids)


def precision_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    if not retrieved_ids:
        return -1.0
    hits = sum(1 for rid in retrieved_ids[:k] if rid in relevant_ids)
    return hits / min(k, len(retrieved_ids))


def mrr(retrieved_ids: list[int], relevant_ids: set[int]) -> float:
    """Mean Reciprocal Rank — rank of the FIRST relevant result."""
    for rank, rid in enumerate(retrieved_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[int], relevant_ids: set[int], k: int) -> float:
    """
    NDCG@k with binary relevance (1 if relevant, 0 if not).
    """
    def dcg(ids: list[int], rel: set[int], k: int) -> float:
        return sum(
            1.0 / math.log2(i + 2)          # +2 because rank starts at 1
            for i, rid in enumerate(ids[:k])
            if rid in rel
        )

    actual  = dcg(retrieved_ids, relevant_ids, k)
    # Ideal: all relevant docs at the top
    ideal   = dcg(list(relevant_ids)[:k], relevant_ids, k)
    return actual / ideal if ideal > 0 else 0.0


# ---------------------------------------------------------------------------
# Relevance detection (keyword fallback when no doc IDs annotated)
# ---------------------------------------------------------------------------

def _keyword_relevant(chunk_content: str, keywords: list[str]) -> bool:
    text = chunk_content.lower()
    return any(kw.lower() in text for kw in keywords)


# ---------------------------------------------------------------------------
# Single query evaluation
# ---------------------------------------------------------------------------

def evaluate_query(
    query_obj: dict,
    k: int,
    retrieval_only: bool,
    user=None,
) -> dict:
    from app.rag.retriever.retriever import search
    from app.rag.retriever.query_parser import detect_query_intent

    query           = query_obj["query"]
    relevant_ids    = set(query_obj.get("relevant_doc_ids") or [])
    rel_keywords    = query_obj.get("relevant_keywords") or []

    t0      = time.time()
    intent  = detect_query_intent(query)
    results = search(query=query, top_k=k, user=user)
    latency = round(time.time() - t0, 3)

    retrieved_doc_ids = [r.doc_id for r in results]

    # Build effective relevant set
    if relevant_ids:
        effective_rel = relevant_ids
    elif rel_keywords:
        # Keyword-based relevance: any result containing the keywords counts
        effective_rel = {
            r.doc_id for r in results
            if _keyword_relevant(r.content, rel_keywords)
        }
    else:
        effective_rel = set()

    rec   = recall_at_k(retrieved_doc_ids, effective_rel, k)
    prec  = precision_at_k(retrieved_doc_ids, effective_rel, k)
    mrr_  = mrr(retrieved_doc_ids, effective_rel)
    ndcg  = ndcg_at_k(retrieved_doc_ids, effective_rel, k)

    answer_preview = ""
    answer_len     = 0
    faithfulness   = None
    confidence     = None

    if not retrieval_only:
        try:
            from app.rag.llm.qa_pipeline import ask
            resp = ask(
                query=query,
                top_k=k,
                user=user,
                run_faithfulness_check=True,
                enable_agent=False,
            )
            answer_preview = resp.answer[:300]
            answer_len     = len(resp.answer)
            faithfulness   = resp.faithfulness
            confidence     = resp.confidence
        except Exception as e:
            answer_preview = f"[ERROR: {e}]"

    return {
        "query":           query,
        "intent_detected": intent,
        "retrieval_count": len(results),
        "sources_used":    [r.file_name for r in results],
        "relevant_ids":    list(effective_rel),
        "recall_at_k":     round(rec,  3),
        "precision_at_k":  round(prec, 3),
        "mrr_score":       round(mrr_, 3),
        "ndcg_at_k":       round(ndcg, 3),
        "latency_s":       latency,
        "answer_preview":  answer_preview,
        "answer_length":   answer_len,
        "faithfulness":    faithfulness,
        "confidence":      confidence,
    }


# ---------------------------------------------------------------------------
# Summary statistics across all queries
# ---------------------------------------------------------------------------

def print_summary(results: list[dict], k: int) -> None:
    def _avg(key: str) -> str:
        vals = [r[key] for r in results if r.get(key) not in (None, -1.0)]
        return f"{sum(vals)/len(vals):.3f}" if vals else "N/A"

    print("\n" + "═" * 60)
    print(f"  RAG EVALUATION SUMMARY  (k={k}, n={len(results)} queries)")
    print("═" * 60)
    print(f"  Recall@{k}      : {_avg('recall_at_k')}")
    print(f"  Precision@{k}   : {_avg('precision_at_k')}")
    print(f"  MRR            : {_avg('mrr_score')}")
    print(f"  NDCG@{k}        : {_avg('ndcg_at_k')}")
    print(f"  Avg latency(s) : {_avg('latency_s')}")
    print(f"  Avg confidence : {_avg('confidence')}")
    print(f"  Avg faithfulness: {_avg('faithfulness')}")
    print("═" * 60)

    # Per-query table
    print(f"\n{'Query':<45} {'R@k':>6} {'P@k':>6} {'MRR':>6} {'Lat':>7}")
    print("-" * 70)
    for r in results:
        q  = r["query"][:43]
        rec = f"{r['recall_at_k']:.2f}"    if r['recall_at_k']    >= 0 else "  N/A"
        pr  = f"{r['precision_at_k']:.2f}" if r['precision_at_k'] >= 0 else "  N/A"
        mr  = f"{r['mrr_score']:.2f}"
        lat = f"{r['latency_s']:.1f}s"
        print(f"{q:<45} {rec:>6} {pr:>6} {mr:>6} {lat:>7}")


# ---------------------------------------------------------------------------
# Template generator
# ---------------------------------------------------------------------------

TEMPLATE = [
    {
        "query": "What is Bluetooth?",
        "relevant_doc_ids": [],
        "relevant_keywords": ["bluetooth", "wireless", "UHF", "IEEE 802.15"]
    },
    {
        "query": "What is Star Topology?",
        "relevant_doc_ids": [],
        "relevant_keywords": ["star topology", "hub", "central"]
    },
    {
        "query": "Explain Mesh Topology",
        "relevant_doc_ids": [],
        "relevant_keywords": ["mesh topology", "host", "dedicated link"]
    },
    {
        "query": "What are Computer Networks?",
        "relevant_doc_ids": [],
        "relevant_keywords": ["computer network", "nodes", "protocol"]
    },
    {
        "query": "List all network topologies",
        "relevant_doc_ids": [],
        "relevant_keywords": ["bus", "ring", "star", "mesh", "tree", "hybrid"]
    },
]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG pipeline")
    parser.add_argument("--queries",          type=str, help="Path to queries JSON file")
    parser.add_argument("--k",                type=int, default=5, help="Top-k for evaluation")
    parser.add_argument("--retrieval-only",   action="store_true", help="Skip LLM, retrieval metrics only")
    parser.add_argument("--out",              type=str, default="eval_results.json")
    parser.add_argument("--generate-template", action="store_true", help="Write a template queries file and exit")
    args = parser.parse_args()

    if args.generate_template:
        out = args.queries or "scripts/eval_queries.json"
        with open(out, "w") as f:
            json.dump(TEMPLATE, f, indent=2)
        print(f"Template written to {out}")
        print("Edit 'relevant_doc_ids' with actual document IDs from your DB,")
        print("or leave empty to use keyword-based relevance.")
        return

    if not args.queries:
        parser.print_help()
        sys.exit(1)

    with open(args.queries) as f:
        queries = json.load(f)

    print(f"Evaluating {len(queries)} queries  (k={args.k}, retrieval_only={args.retrieval_only})\n")

    all_results = []
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q['query'][:60]}…", end=" ", flush=True)
        try:
            r = evaluate_query(q, k=args.k, retrieval_only=args.retrieval_only)
            all_results.append(r)
            print(f"R@{args.k}={r['recall_at_k']:.2f}  P@{args.k}={r['precision_at_k']:.2f}  {r['latency_s']:.1f}s")
        except Exception as e:
            print(f"ERROR: {e}")
            all_results.append({"query": q["query"], "error": str(e)})

    print_summary(all_results, args.k)

    with open(args.out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved → {args.out}")


if __name__ == "__main__":
    main()
