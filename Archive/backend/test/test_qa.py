"""
End-to-end test for the full RAG + LLM pipeline.

Run from the project root:
    python test_qa.py

Prerequisites:
    1. ollama serve          (in another terminal)
    2. ollama pull llama3
    3. Elasticsearch running
    4. At least one document indexed
"""
from __future__ import annotations
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rag.llm.qa_pipeline import ask, retrieve_only

# ---------------------------------------------------------------------------
# Test queries — covers all intent types and army doc varieties
# ---------------------------------------------------------------------------
QUERIES = [
    # Prose / general
    ("documents required for enrolment",          None),
    ("what is the procedure for CASEVAC",         None),

    # Command intent
    ("find command 5 in file commands",            None),
    ("what is ls -al",                             None),

    # List intent
    ("list all network commands",                  None),
    ("show all file commands",                     None),

    # With explicit filters
    ("show me commands",                           {"category": "file_commands"}),
    ("enrolment procedure",                        {"doc_type": "regulation"}),
]


def separator(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_retrieval_only():
    separator("RETRIEVAL ONLY (no LLM)")
    q = "documents required for enrolment"
    results = retrieve_only(query=q, top_k=3, user=None)

    print(f"\nQuery   : {q}")
    print(f"Results : {len(results)}")

    for i, r in enumerate(results, 1):
        print(f"\n  [{i}] Score: {r.score:.3f}")
        print(f"       Title: {r.get_display_title()}")
        print(f"       File : {r.file_name}  Page {r.page_number}")
        if r.is_list_item:
            print(f"       Cmd  : {r.command}  |  Rank #{r.rank_in_section}  |  {r.category}")
        else:
            print(f"       Text : {r.content[:120]}…")


def test_full_pipeline():
    separator("FULL PIPELINE (Retrieval + LLM)")

    for query, filters in QUERIES:
        print(f"\nQuery   : {query}")
        if filters:
            print(f"Filters : {filters}")

        response = ask(query=query, filters=filters, top_k=5, user=None)

        if response.error:
            print(f"❌ Error : {response.error}")
            continue

        print(f"Intent  : {response.intent}")
        print(f"Chunks  : {response.results_count}  Scores: {response.retrieval_scores}")
        print(f"\nAnswer:\n{response.answer}")

        if response.sources:
            print(f"\nSources ({len(response.sources)}):")
            for s in response.sources:
                cmd_info = f"  cmd={s['command']} rank={s['rank']}" if s["is_command"] else ""
                print(f"  • {s['title']}  [{s['file_name']} p{s['page_number']}]{cmd_info}")

        print("-" * 60)


def test_streaming():
    separator("STREAMING (token by token)")
    query = "list all file commands"
    print(f"\nQuery: {query}")
    print("Tokens: ", end="", flush=True)

    token_iter = ask(query=query, top_k=5, user=None, stream=True)

    # If Ollama is down, ask() returns QAResponse not an iterator
    if hasattr(token_iter, "error"):
        print(f"\n❌ {token_iter.error}")
        return

    for token in token_iter:
        print(token, end="", flush=True)

    print("\n[stream done]")


if __name__ == "__main__":
    test_retrieval_only()
    test_full_pipeline()
    test_streaming()