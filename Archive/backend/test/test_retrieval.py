import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.rag.retriever.retriever import search

def test():

    query = "documents required for enrolment"

    results = search(query=query, user=None)

    print("\n🔍 QUERY:", query)
    print("="*50)

    if not results:
        print("❌ No results found")
        return

    for i, r in enumerate(results, 1):
        print(f"\nResult {i}")
        print("Score:", r.score)
        print("Doc ID:", r.doc_id)
        print("Text:", r.content[:200])


if __name__ == "__main__":
    test()