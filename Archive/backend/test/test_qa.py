"""
End-to-end test for the full RAG + LLM pipeline.
Run: python test/test_qa.py
"""
from __future__ import annotations
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.rag.llm.qa_pipeline import ask, retrieve_only

QUERIES = [
    "documents required for enrolment",
    "what is ls -al",
    "show all file commands",
    "find command 5 in file commands",
    "list all network commands",
    "enrolment procedure indian army",
    "what is the procedure for CASEVAC",
]

def separator(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

def test_retrieval_only():
    separator("RETRIEVAL ONLY (no LLM)")
    q = "documents required for enrolment"
    results = retrieve_only(query=q, top_k=3, user=None)
    print(f"\nQuery: {q}  Results: {len(results)}")
    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] Score: {r.score:.3f}  File: {r.file_name[-50:]}  Page: {r.page_number}")
        if r.is_list_item:
            print(f"       Cmd: {r.command}  Rank #{r.rank_in_section}  {r.category}")
        else:
            print(f"       Text: {r.content[:120]}...")

def test_full_pipeline():
    separator("FULL PIPELINE (Retrieval + LLM)")
    for query in QUERIES:
        print(f"\nQuery: {query}")
        response = ask(query=query, filters=None, top_k=3, user=None, run_faithfulness_check=True)
        if response.error:
            print(f"ERROR: {response.error}")
            continue
        print(f"Intent: {response.intent}  Faithful: {response.faithfulness:.2f} {'OK' if response.is_faithful else 'WARN'}  Chunks: {response.results_count}")
        print(f"\nAnswer:\n{response.answer}")
        if response.sources:
            print(f"\nSources ({len(response.sources)}):")
            for s in response.sources:
                print(f"  - {s['file_name'][-45:]} p{s['page_number']} score={s['score']}")
        print("-"*60)

def test_streaming():
    separator("STREAMING")
    query = "show all file commands"
    print(f"\nQuery: {query}\nTokens: ", end="", flush=True)
    result = ask(query=query, top_k=3, user=None, stream=True)
    if hasattr(result, "error"):
        print(f"\nERROR: {result.error}")
        return
    for token in result:
        print(token, end="", flush=True)
    print("\n[stream done]")

if __name__ == "__main__":
    test_retrieval_only()
    test_full_pipeline()
    test_streaming()