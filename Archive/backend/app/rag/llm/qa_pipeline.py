from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from app.rag.retriever.retriever import search, SearchResult
from app.rag.retriever.query_parser import detect_query_intent
from app.rag.llm.llm_client import chat, is_ollama_running
from app.rag.llm.context_builder import build_context, get_source_summary
from app.rag.llm.prompt_builder import build_system_prompt, build_user_prompt


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class QAResponse:
    """
    Structured response from the full RAG + LLM pipeline.

    Fields
    ------
    answer          : LLM-generated answer text
    query           : Original user query
    sources         : Deduplicated source citations (file, page, section, score)
    results_count   : Number of chunks retrieved and sent to LLM
    retrieval_scores: Per-chunk relevance scores (for debugging / UI confidence)
    model           : Ollama model name used
    intent          : Detected query intent (command / list / prose / mixed)
    error           : Set when the pipeline could not complete normally
    """
    answer:            str
    query:             str
    sources:           List[dict]        = field(default_factory=list)
    results_count:     int               = 0
    retrieval_scores:  List[float]       = field(default_factory=list)
    model:             str               = "llama3:latest"
    intent:            str               = "mixed"
    error:             Optional[str]     = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ask(
    query: str,
    filters: dict | None = None,
    top_k: int = 5,
    user=None,
    model: str = "llama3:latest",
    stream: bool = False,
) -> QAResponse | Iterator[str]:
    """
    Full RAG → LLM pipeline for a single user query.

    Pipeline
    --------
    1.  Guard   — check Ollama is running
    2.  Detect  — query intent (command / list / prose / mixed)
    3.  Retrieve — hybrid ES search + reranking (your existing retriever)
    4.  Build context — format results into a context string
    5.  Build prompts — system (army rules + branch + intent) + user (context + query)
    6.  LLM call — llama3 via Ollama
    7.  Return  — QAResponse with answer + sources + scores

    Args:
        query   : Natural language question from the user
        filters : Explicit ES filters {branch, doc_type, year, section,
                  rank_in_section, category, command}
        top_k   : Number of chunks to retrieve (5 is safe for llama3 8B)
        user    : Authenticated user object (for RBAC filtering)
        model   : Ollama model name
        stream  : If True, returns a token Iterator instead of QAResponse

    Returns:
        QAResponse  — when stream=False (default)
        Iterator[str] — token stream when stream=True
                        Note: sources/metadata are NOT available in stream mode;
                        fetch them separately via retrieve_only() if needed.
    """

    # ── 1. Guard ─────────────────────────────────────────────────────────
    if not is_ollama_running():
        return QAResponse(
            answer="",
            query=query,
            model=model,
            error=(
                "Ollama is not running. "
                "Start it with:  ollama serve\n"
                "Then pull the model:  ollama pull llama3"
            ),
        )

    # ── 2. Intent detection ───────────────────────────────────────────────
    intent = detect_query_intent(query)
    print(f"[QA] Query: {query!r}  |  Intent: {intent}")

    # ── 3. Retrieve ───────────────────────────────────────────────────────
    results: List[SearchResult] = search(
        query=query,
        filters=filters,
        top_k=top_k,
        user=user,
    )

    if not results:
        return QAResponse(
            answer=(
                "No relevant documents were found for your query. "
                "Please try rephrasing or check that the relevant documents "
                "have been uploaded and indexed."
            ),
            query=query,
            model=model,
            intent=intent,
        )

    print(f"[QA] Retrieved {len(results)} chunks")

    # ── 4. Build context ──────────────────────────────────────────────────
    context = build_context(results, query)

    # ── 5. Build prompts ──────────────────────────────────────────────────
    system_prompt = build_system_prompt(results=results, intent=intent)
    user_prompt   = build_user_prompt(query=query, context=context)

    # ── 6. LLM call ───────────────────────────────────────────────────────
    print(f"[QA] Calling {model} (stream={stream})…")

    if stream:
        # Return raw token iterator — caller handles SSE/WebSocket framing
        return chat(
            prompt=user_prompt,
            system=system_prompt,
            model=model,
            stream=True,
        )

    answer = chat(
        prompt=user_prompt,
        system=system_prompt,
        model=model,
        stream=False,
    )

    print(f"[QA] Answer generated ({len(answer)} chars)")

    # ── 7. Return structured response ─────────────────────────────────────
    return QAResponse(
        answer=answer,
        query=query,
        sources=get_source_summary(results),
        results_count=len(results),
        retrieval_scores=[round(r.score, 3) for r in results],
        model=model,
        intent=intent,
    )


def retrieve_only(
    query: str,
    filters: dict | None = None,
    top_k: int = 5,
    user=None,
) -> List[SearchResult]:
    """
    Run retrieval only — no LLM call.

    Useful for:
    - Streaming endpoints that need source metadata alongside token stream
    - Debugging retrieval quality
    - Building a "preview sources" feature before the full answer loads

    Returns
    -------
    List[SearchResult] in reranked order.
    """
    return search(query=query, filters=filters, top_k=top_k, user=user)