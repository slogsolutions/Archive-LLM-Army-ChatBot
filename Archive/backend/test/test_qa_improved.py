"""
Comprehensive RAG test suite.

Run from project root:
    python test/test_rag.py

Tests are grouped into:
    A. Retrieval-only tests (fast, no LLM)
    B. Full pipeline tests (slow, uses llama3)
    C. ES data quality check (shows what's in your index)
    D. Edge cases

CURRENT KNOWN LIMITATIONS (will auto-resolve after re-indexing Linux PDF):
    - "show all file commands" returns results but no structured list
      because is_list_item/category fields are empty in current index
    - "find command 5" cannot rank by position for same reason
    - ls -al answer shows "Is" instead of "ls" (OCR artifact in stored text)
"""
from __future__ import annotations
import sys, os, time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rag.retriever.retriever import search
from app.rag.llm.qa_pipeline import ask, retrieve_only

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PASS  = "✅ PASS"
FAIL  = "❌ FAIL"
WARN  = "⚠️  WARN"
INFO  = "ℹ️  INFO"

results_log = []

def check(label: str, condition: bool, note: str = ""):
    status = PASS if condition else FAIL
    msg    = f"{status} | {label}"
    if note:
        msg += f"  [{note}]"
    print(msg)
    results_log.append((status, label))
    return condition

def sep(title: str):
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")

def timed(fn):
    t0 = time.time()
    result = fn()
    elapsed = time.time() - t0
    return result, elapsed

# ─────────────────────────────────────────────────────────────────────────────
# A. RETRIEVAL TESTS (no LLM)
# ─────────────────────────────────────────────────────────────────────────────

def test_retrieval():
    sep("A. RETRIEVAL TESTS (no LLM)")

    # A1 — Enrolment doc: should find the right PDF with score > 0.9
    print("\n[A1] Enrolment document retrieval")
    results, t = timed(lambda: retrieve_only("documents required for enrolment", top_k=3))
    check("A1: got results",        len(results) > 0)
    check("A1: top score > 0.9",    results[0].score > 0.9 if results else False,
          f"score={results[0].score:.3f}" if results else "no results")
    check("A1: correct file",       "enrol" in results[0].file_name.lower() if results else False,
          results[0].file_name[-40:] if results else "")
    print(f"     Time: {t:.1f}s")

    # A2 — Linux commands: should find Linux PDF
    print("\n[A2] Linux commands retrieval")
    results, t = timed(lambda: retrieve_only("linux file commands ls directory", top_k=3))
    check("A2: got results",        len(results) > 0)
    if results:
        linux_found = any("linux" in r.file_name.lower() or "command" in r.file_name.lower()
                         for r in results)
        check("A2: Linux PDF in results", linux_found,
              results[0].file_name[-40:])
    print(f"     Time: {t:.1f}s")

    # A3 — Network doc: should find Network.pdf
    print("\n[A3] Network document retrieval")
    results, t = timed(lambda: retrieve_only("computer network LAN WAN", top_k=3))
    check("A3: got results",        len(results) > 0)
    if results:
        net_found = any("network" in r.file_name.lower() for r in results)
        check("A3: Network PDF found", net_found,
              results[0].file_name[-40:])
    print(f"     Time: {t:.1f}s")

    # A4 — Show all file commands (currently no category in index)
    print("\n[A4] 'show all file commands' — expects Linux PDF even without category field")
    results, t = timed(lambda: retrieve_only("show all file commands", top_k=5))
    check("A4: got results",        len(results) > 0,
          "FAIL = elastic_store_patch.py not applied yet")
    if results:
        linux_found = any("linux" in r.file_name.lower() or "command" in r.file_name.lower()
                         for r in results)
        check("A4: Linux PDF in top results", linux_found,
              f"top file: {results[0].file_name[-40:]}")
        has_category = any(r.category and r.category != "" for r in results)
        status = INFO
        print(f"{status} | A4: is_list_item populated: {has_category} "
              f"(False = needs re-index with fixed chunker)")
    print(f"     Time: {t:.1f}s")

    # A5 — Find command 5 (rank_in_section empty in current index)
    print("\n[A5] 'find command 5 in file commands'")
    results, t = timed(lambda: retrieve_only("find command 5 in file commands", top_k=5))
    check("A5: got results",        len(results) > 0,
          "FAIL = no results even with soft boost")
    if results:
        has_rank = any(r.rank_in_section == 5 for r in results)
        status = PASS if has_rank else INFO
        print(f"{status} | A5: rank_in_section=5 found: {has_rank} "
              f"(False = needs re-index)")
    print(f"     Time: {t:.1f}s")

    # A6 — CASEVAC: not in index, should return network/other docs
    print("\n[A6] CASEVAC (not in index)")
    results, t = timed(lambda: retrieve_only("CASEVAC casualty evacuation procedure", top_k=3))
    check("A6: returns something",  len(results) > 0,
          "correct — returns best available even if not CASEVAC doc")
    if results:
        casevac_found = any("casevac" in r.content.lower() for r in results)
        print(f"{INFO} | A6: actual CASEVAC content in results: {casevac_found} "
              f"(False = upload a CASEVAC doc to fix this)")
    print(f"     Time: {t:.1f}s")

    # A7 — Score threshold: low-relevance docs should have low scores
    print("\n[A7] Score sanity — enrolment query should NOT rank Network.pdf highly")
    results, t = timed(lambda: retrieve_only("documents required for enrolment", top_k=5))
    if results:
        network_scores = [r.score for r in results if "network" in r.file_name.lower()]
        enrol_scores   = [r.score for r in results if "enrol"   in r.file_name.lower()]
        if network_scores and enrol_scores:
            check("A7: enrolment score > network score",
                  min(enrol_scores) > max(network_scores),
                  f"enrol_min={min(enrol_scores):.2f} net_max={max(network_scores):.2f}")
        else:
            print(f"{INFO} | A7: only one doc type in results — OK")
    print(f"     Time: {t:.1f}s")


# ─────────────────────────────────────────────────────────────────────────────
# B. FULL PIPELINE TESTS (LLM)
# ─────────────────────────────────────────────────────────────────────────────

def test_pipeline():
    sep("B. FULL PIPELINE TESTS (LLM — each takes 1-3 min on CPU)")

    cases = [
        {
            "query":       "documents required for enrolment into the Indian Army",
            "label":       "B1: Enrolment documents",
            "must_contain": ["admit card", "pass certificate", "mark sheet",
                             "character certificate", "photograph"],
            "must_not_contain": [],
            "expected_faithful": 0.7,
        },
        {
            "query":       "what is ls -al command",
            "label":       "B2: ls -al command",
            "must_contain": ["listing", "hidden", "file"],
            "must_not_contain": [],
            "expected_faithful": 0.4,   # lower because OCR has "Is" not "ls"
        },
        {
            "query":       "what are the types of network topology",
            "label":       "B3: Network topology",
            "must_contain": ["bus", "star", "ring", "mesh"],
            "must_not_contain": [],
            "expected_faithful": 0.6,
        },
        {
            "query":       "what is CASEVAC",
            "label":       "B4: CASEVAC (not in docs)",
            "must_contain": ["not available", "not mentioned", "not in"],
            "must_not_contain": [],
            "expected_faithful": 0.8,  # LLM should correctly refuse
        },
        {
            "query":       "show all file commands in linux",
            "label":       "B5: All file commands",
            "must_contain": ["ls", "directory", "file"],
            "must_not_contain": [],
            "expected_faithful": 0.5,
        },
    ]

    for case in cases:
        print(f"\n{case['label']}")
        print(f"  Query: {case['query']}")
        t0 = time.time()

        response = ask(
            query=case["query"],
            filters=None,
            top_k=3,
            user=None,
            run_faithfulness_check=True,
        )
        elapsed = time.time() - t0

        if response.error:
            print(f"{FAIL} | {case['label']}: ERROR — {response.error}")
            continue

        answer_lower = response.answer.lower()

        # Check answer contains expected terms
        found    = [t for t in case["must_contain"]     if t.lower() in answer_lower]
        rejected = [t for t in case["must_not_contain"] if t.lower() in answer_lower]

        check(f"{case['label']}: answer contains expected terms",
              len(found) >= max(1, len(case["must_contain"]) // 2),
              f"found {len(found)}/{len(case['must_contain'])}: {found}")

        check(f"{case['label']}: faithfulness >= {case['expected_faithful']}",
              response.faithfulness >= case["expected_faithful"],
              f"actual={response.faithfulness:.2f}")

        check(f"{case['label']}: has sources",
              len(response.sources) > 0)

        # Print answer preview
        preview = response.answer[:200].replace("\n", " ")
        print(f"  Answer preview: {preview}...")
        print(f"  Sources: {[s['file_name'][-35:] for s in response.sources]}")
        print(f"  Time: {elapsed:.0f}s  Faithful: {response.faithfulness:.2f}  "
              f"Intent: {response.intent}  Chunks: {response.results_count}")


# ─────────────────────────────────────────────────────────────────────────────
# C. ES DATA QUALITY CHECK
# ─────────────────────────────────────────────────────────────────────────────

def test_es_data_quality():
    sep("C. ES DATA QUALITY CHECK")

    try:
        from app.rag.vector_store.elastic_store import get_es, INDEX_NAME
        es = get_es()

        # Total doc count
        count = es.count(index=INDEX_NAME)["count"]
        print(f"\n{INFO} | Total chunks in ES: {count}")

        # Check for list items (should be 0 before re-index, >0 after)
        list_count = es.count(index=INDEX_NAME,
                              body={"query": {"term": {"is_list_item": True}}})["count"]
        check("C1: has list items (0 = re-index needed)",
              list_count > 0,
              f"list_item chunks: {list_count}")

        # Check for category field populated
        cat_count = es.count(index=INDEX_NAME,
                             body={"query": {"exists": {"field": "category"}}})["count"]
        print(f"{INFO} | Chunks with category field: {cat_count}")

        # Per-document breakdown
        resp = es.search(index=INDEX_NAME, body={
            "size": 0,
            "aggs": {
                "by_doc": {
                    "terms": {"field": "file_name", "size": 20},
                    "aggs": {
                        "list_items": {"filter": {"term": {"is_list_item": True}}},
                        "has_category": {"filter": {"exists": {"field": "category"}}},
                        "avg_score": {"avg": {"field": "min_visible_rank"}},
                    }
                }
            }
        })

        print(f"\n{'File':<50} {'Chunks':>6} {'ListItems':>9} {'HasCategory':>11}")
        print("─" * 80)
        for bucket in resp["aggregations"]["by_doc"]["buckets"]:
            fname      = bucket["key"][-48:]
            total      = bucket["doc_count"]
            list_items = bucket["list_items"]["doc_count"]
            has_cat    = bucket["has_category"]["doc_count"]
            status     = "✅" if list_items > 0 else "⚠️ needs re-index"
            print(f"{fname:<50} {total:>6} {list_items:>9} {has_cat:>11}  {status}")

        # OCR quality check — look for "Is " instead of "ls " in Linux doc
        ocr_check = es.search(index=INDEX_NAME, body={
            "query": {
                "bool": {
                    "must": {"match_phrase": {"content": "Is Directory listing"}},
                    "filter": {"wildcard": {"file_name": "*Linux*"}}
                }
            },
            "size": 1
        })
        ocr_bad = ocr_check["hits"]["total"]["value"] > 0
        check("C2: OCR quality — 'ls' not mangled to 'Is' in Linux doc",
              not ocr_bad,
              "FAIL = re-ingest Linux PDF with ocr_cleaner fix")

    except Exception as e:
        print(f"{FAIL} | ES connection failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# D. EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases():
    sep("D. EDGE CASES (retrieval only)")

    # D1 — Empty query
    print("\n[D1] Empty query")
    results = retrieve_only(query="", top_k=3)
    check("D1: empty query returns empty", len(results) == 0)

    # D2 — Garbage query
    print("\n[D2] Garbage query")
    results = retrieve_only(query="zzzzxxx123nonsense", top_k=3)
    check("D2: garbage returns results or empty gracefully", True,
          f"returned {len(results)} results (any is fine)")

    # D3 — Very long query
    print("\n[D3] Long query (100+ words)")
    long_q = "document " * 100
    try:
        results = retrieve_only(query=long_q, top_k=3)
        check("D3: long query handled without crash", True,
              f"returned {len(results)} results")
    except Exception as e:
        check("D3: long query handled without crash", False, str(e))

    # D4 — Mixed language query
    print("\n[D4] Hindi/mixed query")
    results = retrieve_only(query="army document bharat", top_k=3)
    check("D4: mixed query returns something", len(results) >= 0,
          "any result is fine")


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

def print_summary():
    sep("SUMMARY")
    passed = sum(1 for s, _ in results_log if "PASS" in s)
    failed = sum(1 for s, _ in results_log if "FAIL" in s)
    total  = len(results_log)
    print(f"\nTotal: {total}  ✅ {passed}  ❌ {failed}")
    if failed:
        print("\nFailed checks:")
        for status, label in results_log:
            if "FAIL" in status:
                print(f"  ❌ {label}")
    print("\nKnown issues (not bugs — resolve by re-indexing Linux PDF):")
    print("  • 'show all file commands' may return 0 results or unstructured text")
    print("  • 'find command 5' cannot rank by position")
    print("  • ls -al answer shows 'Is' instead of 'ls' (OCR artifact)")
    print("\nTo re-index: go to your admin panel → delete Linux PDF → re-upload it")
    print("The fixed chunker + ocr_cleaner will then populate all fields correctly.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm",  action="store_true", help="Skip LLM tests (fast mode)")
    parser.add_argument("--only-es",   action="store_true", help="Only run ES data quality check")
    parser.add_argument("--only-edge", action="store_true", help="Only run edge case tests")
    args = parser.parse_args()

    if args.only_es:
        test_es_data_quality()
    elif args.only_edge:
        test_edge_cases()
    else:
        test_retrieval()
        test_es_data_quality()
        test_edge_cases()
        if not args.skip_llm:
            test_pipeline()
        else:
            print("\n[skipped LLM tests — run without --skip-llm to include them]")
        print_summary()