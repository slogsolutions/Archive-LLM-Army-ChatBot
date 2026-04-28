"""
Run the offline RAG evaluation suite.

Usage (from Archive/backend/ directory):
    python scripts/run_eval.py

The script sends real queries through the full pipeline (Elasticsearch + Ollama)
and reports metrics: intent accuracy, recall@5, keyword coverage, latency.

Add or edit TestCases below to match documents you have indexed.
Set relevant_doc_ids from your actual Postgres document IDs if you want
retrieval metrics (recall@5, MRR, NDCG). Leave empty to skip those metrics.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.eval.evaluator import RAGEvaluator, TestCase

# ---------------------------------------------------------------------------
# Define test cases — edit to match your indexed documents
# ---------------------------------------------------------------------------
TEST_CASES = [
    # --- Definition queries (intent: prose) ---
    TestCase(
        query             = "What is Bluetooth?",
        expected_keywords = ["wireless", "short-range", "UHF", "IEEE"],
        expected_intent   = "prose",
        description       = "definition — networking doc",
    ),
    TestCase(
        query             = "What is Star Topology?",
        expected_keywords = ["central", "hub", "node", "switch"],
        expected_intent   = "prose",
        description       = "definition — networking topology",
    ),
    TestCase(
        query             = "What are Computer Networks?",
        expected_keywords = ["interconnected", "devices", "communicate", "data"],
        expected_intent   = "prose",
        description       = "broad definition query",
    ),
    TestCase(
        query             = "Explain Mesh Topology",
        expected_keywords = ["every", "host", "connections", "dedicated"],
        expected_intent   = "prose",
        description       = "explain query",
    ),
    TestCase(
        query             = "What is Wi-Fi?",
        expected_keywords = ["wireless", "fidelity", "IEEE", "802.11"],
        expected_intent   = "prose",
        description       = "Wi-Fi definition",
    ),

    # --- List / enumeration queries (intent: list) ---
    TestCase(
        query             = "List all network topologies",
        expected_keywords = ["bus", "ring", "star", "mesh", "tree"],
        expected_intent   = "list",
        description       = "full enumeration query",
    ),
    TestCase(
        query             = "Show all file commands",
        expected_keywords = ["ls", "cd", "mkdir"],
        expected_intent   = "list",
        description       = "list CLI commands (will fail if no cmd doc indexed)",
    ),

    # --- Not-found queries (should gracefully say not found) ---
    TestCase(
        query             = "What is CASEVAC procedure in infantry?",
        expected_keywords = ["not available"],
        expected_intent   = "prose",
        description       = "not-found query — no infantry doc indexed",
    ),

    # --- Follow-up / conversational (intent: mixed/prose) ---
    TestCase(
        query             = "How does Wi-Fi differ from Bluetooth?",
        expected_keywords = ["wireless", "range", "frequency"],
        expected_intent   = "prose",
        description       = "comparison query",
    ),
]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    evaluator = RAGEvaluator(output_path="eval_results.json")
    evaluator.run(TEST_CASES, user=None)   # user=None skips RBAC
