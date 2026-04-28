from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Iterator, List, Optional

from app.rag.retriever.retriever import search, SearchResult
from app.rag.retriever.query_parser import detect_query_intent
from app.rag.llm.llm_client import chat, is_ollama_running
from app.rag.llm.context_builder import build_context, get_source_summary
from app.rag.llm.prompt_builder import build_system_prompt, build_user_prompt
from app.rag.llm.faithfulness_guard import check_faithfulness, safe_answer
from app.rag.llm.citation_injector import inject_citations
from app.rag.llm.conversation_memory import memory as conv_memory
from app.rag.llm.confidence import (
    compute_confidence, build_rejection_message, build_warning_note, keyword_coverage
)
from app.rag.llm import agent_loop


@dataclass
class QAResponse:
    answer:            str
    query:             str
    sources:           List[dict]    = field(default_factory=list)
    results_count:     int           = 0
    retrieval_scores:  List[float]   = field(default_factory=list)
    model:             str           = "llama3:latest"
    intent:            str           = "mixed"
    faithfulness:      float         = 1.0
    is_faithful:       bool          = True
    confidence:        float         = 1.0   # composite quality score 0-1
    was_rejected:      bool          = False  # blocked by confidence gate
    hops:              int           = 0
    latency_s:         float         = 0.0
    error:             Optional[str] = None


def ask(
    query: str,
    filters: dict | None = None,
    top_k: int = 5,
    user=None,
    model: str = "llama3:latest",
    stream: bool = False,
    run_faithfulness_check: bool = True,
    session_id: str | None = None,
    enable_agent: bool = True,
) -> "QAResponse | Iterator[str]":
    """
    Full production RAG + LLM pipeline.

    Stages
    ------
    1  Ollama guard
    2  Intent detection
    3  Conversation memory — inject prior Q&A turns into the prompt
    4  Retrieval (parse → HyDE → embed → hybrid BM25+KNN → cross-encoder rerank)
    5  Agentic multi-hop — re-search if first answer is insufficient
    6  Context building (list formatter or prose formatter)
    7  Prompt construction (intent-aware system + user prompts)
    8  LLM generation
    9a Faithfulness guard (skipped for list intent)
    9b Citation injection
    10 Conversation memory — record this turn
    11 Return QAResponse
    """
    t_start = time.time()

    # ── Stage 1 ────────────────────────────────────────────────────────────
    if not is_ollama_running():
        return QAResponse(
            answer="", query=query, model=model,
            error="Ollama is not running. Run: ollama serve && ollama pull llama3",
        )

    # ── Stage 2 ────────────────────────────────────────────────────────────
    intent = detect_query_intent(query)
    print(f"[QA] Query={query!r}  Intent={intent}")

    # ── Stage 3: Conversation context ─────────────────────────────────────
    history_block = ""
    if session_id:
        history_block = conv_memory.get_context_block(session_id)
        if history_block:
            print(f"[QA] Injecting conversation history for session={session_id!r}")

    # ── Stage 4: Retrieval ─────────────────────────────────────────────────
    effective_top_k = top_k * 4 if intent == "list" else top_k
    results: List[SearchResult] = search(
        query=query, filters=filters, top_k=effective_top_k, user=user,
    )

    if not results:
        return QAResponse(
            answer=(
                "No relevant documents found. "
                "Try rephrasing or ensure documents are indexed."
            ),
            query=query, model=model, intent=intent,
        )

    print(f"[QA] {len(results)} chunks retrieved")

    # ── Stage 5: Context + first-pass LLM call ────────────────────────────
    context        = build_context(results, query)
    system_prompt  = build_system_prompt(results=results, intent=intent)
    user_prompt    = _build_prompt_with_history(query, context, history_block)

    print("─" * 60)
    print(f"[PROMPT system]\n{system_prompt}\n")
    print(f"[PROMPT user]\n{user_prompt}\n")
    print("─" * 60)

    if stream:
        return chat(prompt=user_prompt, system=system_prompt, model=model, stream=True)

    print(f"[QA] Calling {model}  stream=False")
    raw_answer = chat(prompt=user_prompt, system=system_prompt, model=model)
    print(f"[QA] Raw answer: {len(raw_answer)} chars")
    print(f"[RAW ANSWER]\n{raw_answer}\n")
    print("─" * 60)

    # ── Stage 5b: Agentic multi-hop ───────────────────────────────────────
    # NOTE: retry-on-not-available removed — it triggered an extra Ollama
    # call (~100-200s on CPU) even when retrieval was the root cause.
    # Better retrieval (dedup fix + no HyDE) makes the LLM answer correctly
    # in the first pass, so the retry was masking rather than fixing issues.
    hops = 0
    if enable_agent:
        results, hops = agent_loop.run(
            original_query  = query,
            initial_results = results,
            initial_answer  = raw_answer,
            filters         = filters,
            user            = user,
            model           = model,
            intent          = intent,
        )
        if hops > 0:
            # Rebuild context and regenerate answer with expanded results
            context     = build_context(results, query)
            user_prompt = _build_prompt_with_history(query, context, history_block)
            print(f"[QA] Re-answering after {hops} hop(s)…")
            raw_answer  = chat(prompt=user_prompt, system=system_prompt, model=model)
            print(f"[QA] Hop answer: {len(raw_answer)} chars")
            print(f"[RAW ANSWER (hop)]\n{raw_answer}\n")
            print("─" * 60)

    # ── Stage 9a: Faithfulness guard ──────────────────────────────────────
    faith_result   = None
    guarded_answer = raw_answer

    if run_faithfulness_check and intent != "list":
        print("[QA] Running faithfulness check…")
        # run_llm_check=False: the LLM faithfulness call adds ~100s on CPU.
        # Lexical check (~0ms) is sufficient — it catches the most common
        # hallucinations (answer words not in context).
        faith_result   = check_faithfulness(
            answer=raw_answer, results=results,
            run_llm_check=False, model=model,
        )
        guarded_answer = safe_answer(raw_answer, faith_result)
        flag = "✅" if faith_result.is_faithful else "⚠️"
        print(f"[QA] Faithfulness: {faith_result.confidence:.2f} {flag} ({faith_result.method})")
        if faith_result.flagged_claims:
            print(f"[QA] Flagged: {faith_result.flagged_claims[:2]}")

    # ── Stage 9b: Citation injection ──────────────────────────────────────
    sources      = get_source_summary(results)
    final_answer = inject_citations(guarded_answer, sources)

    print(f"[FINAL ANSWER]\n{final_answer}\n")
    print("─" * 60)

    # ── Stage 9c: Confidence scoring + rejection gate ─────────────────────
    faith_score = faith_result.confidence if faith_result else 1.0
    cr = compute_confidence(
        results=results,
        answer=final_answer,
        faithfulness=faith_score,
    )
    print(f"[QA] Confidence: {cr.score:.2f} ({cr.level}){' ← REJECTED' if cr.rejected else ''}")
    if cr.reason:
        print(f"[QA] Confidence reason: {cr.reason}")

    if cr.rejected:
        final_answer = build_rejection_message(cr, query)
    elif cr.level == "moderate":
        final_answer = final_answer + build_warning_note(cr)

    # ── Stage 10: Store conversation turn ────────────────────────────────
    if session_id:
        conv_memory.add_turn(session_id, query, final_answer)

    # ── Stage 11: Persist RAGLog (non-blocking best-effort) ───────────────
    latency = round(time.time() - t_start, 2)
    _write_rag_log(
        query=query,
        intent=intent,
        results=results,
        sources=sources,
        final_answer=final_answer,
        faith_score=faith_score,
        cr=cr,
        model=model,
        session_id=session_id,
        user=user,
        latency_s=latency,
        was_rejected=cr.rejected,
    )

    # ── Stage 12 ──────────────────────────────────────────────────────────
    return QAResponse(
        answer           = final_answer,
        query            = query,
        sources          = sources,
        results_count    = len(results),
        retrieval_scores = [round(r.score, 3) for r in results],
        model            = model,
        intent           = intent,
        faithfulness     = faith_score,
        is_faithful      = faith_result.is_faithful if faith_result else True,
        confidence       = cr.score,
        was_rejected     = cr.rejected,
        hops             = hops,
        latency_s        = latency,
    )


def retrieve_only(
    query: str,
    filters: dict | None = None,
    top_k: int = 5,
    user=None,
) -> List[SearchResult]:
    """Retrieval only — no LLM. Used for streaming source preview."""
    return search(query=query, filters=filters, top_k=top_k, user=user)


def _write_rag_log(
    query: str,
    intent: str,
    results: List[SearchResult],
    sources: List[dict],
    final_answer: str,
    faith_score: float,
    cr,
    model: str,
    session_id: str | None,
    user,
    latency_s: float,
    was_rejected: bool,
) -> None:
    """
    Persist a RAGLog row — best-effort, never raises.
    Called at the end of every ask() regardless of outcome.
    Provides the audit trail required for military deployments.
    """
    import json
    try:
        from app.core.database import SessionLocal
        from app.models.rag_log import RAGLog
        from app.rag.llm.confidence import keyword_coverage

        ctx_text = " ".join(r.content for r in results)
        kw_cov   = keyword_coverage(query, ctx_text)
        scores   = [r.score for r in results]

        status = "rejected" if was_rejected else (
            "not_found" if not results else "ok"
        )

        log = RAGLog(
            query            = query[:1000],
            intent           = intent,
            session_id       = session_id,
            user_id          = user.id if user else None,
            retrieval_count  = len(results),
            unique_sources   = len({r.doc_id for r in results}),
            top_score        = round(scores[0], 3) if scores else None,
            avg_score        = round(sum(scores) / len(scores), 3) if scores else None,
            sources_json     = json.dumps([s.get("file_name") for s in sources[:10]]),
            answer_preview   = final_answer[:500],
            answer_length    = len(final_answer),
            confidence       = cr.score,
            faithfulness     = faith_score,
            keyword_coverage = kw_cov,
            was_rejected     = was_rejected,
            status           = status,
            latency_s        = latency_s,
            model            = model,
            method           = "sync",
        )
        db = SessionLocal()
        try:
            db.add(log)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[QA] RAGLog write failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_prompt_with_history(
    query: str,
    context: str,
    history_block: str,
) -> str:
    """
    Prepend conversation history to the standard user prompt so the LLM
    can resolve references like "elaborate on point 2" or "what about its
    advantages?".  History is clearly labelled and comes BEFORE the context
    so the LLM treats context documents as the authoritative source.
    """
    base = build_user_prompt(query=query, context=context)
    if not history_block:
        return base
    return f"{history_block}\n{base}"
