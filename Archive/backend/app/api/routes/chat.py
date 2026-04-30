from __future__ import annotations
import asyncio
import json
from typing import Optional, Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.rag.llm.qa_pipeline import ask, QAResponse
from app.core.deps import get_current_user
router = APIRouter() 
# router = APIRouter(prefix="/api/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class Filters(BaseModel):
    """Optional structured filters passed directly to Elasticsearch."""
    branch:           Optional[str]  = None
    doc_type:         Optional[str]  = None
    year:             Optional[int]  = None
    section:          Optional[str]  = None
    rank_in_section:  Optional[int]  = None
    category:         Optional[str]  = None
    command:          Optional[str]  = None
    hq_id:            Optional[int]  = None
    unit_id:          Optional[int]  = None


class ChatRequest(BaseModel):
    query:      str     = Field(..., min_length=1, max_length=1000)
    filters:    Filters = Field(default_factory=Filters)
    top_k:      int     = Field(default=5, ge=1, le=20)
    model:      str     = Field(default="llama3:latest")
    stream:     bool    = Field(default=False)
    session_id: Optional[str] = Field(default=None, max_length=128)
    enable_agent: bool  = Field(default=True)


class SourceCitation(BaseModel):
    doc_id:      int
    file_name:   str
    page_number: int
    section:     str
    branch:      str
    doc_type:    str
    year:        Optional[int]
    score:       float
    title:       str
    command:     Optional[str]
    rank:        Optional[int]
    category:    Optional[str]
    is_command:  bool


class ChatResponse(BaseModel):
    answer:           str
    query:            str
    sources:          list[SourceCitation]
    results_count:    int
    retrieval_scores: list[float]
    model:            str
    intent:           str
    hops:             int           = 0
    session_id:       Optional[str] = None
    error:            Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=ChatResponse, summary="Non-streaming chat")
def chat_endpoint(
    req: ChatRequest,
    user=Depends(get_current_user),
):
    """
    Full RAG + LLM answer.

    NOTE: intentionally `def` (not `async def`) so FastAPI runs this in its
    thread pool. The RAG pipeline makes long blocking calls (embedding model
    inference, Ollama, Elasticsearch, SQLAlchemy) that must NOT run on the
    asyncio event loop — they would stall the entire server.
    """
    filters_dict = {
        k: v for k, v in req.filters.model_dump().items()
        if v is not None
    } or None

    response: QAResponse = ask(
        query=req.query,
        filters=filters_dict,
        top_k=req.top_k,
        user=user,
        model=req.model,
        stream=False,
        session_id=req.session_id,
        enable_agent=req.enable_agent,
    )

    if response.error and "not running" in response.error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.error,
        )

    return ChatResponse(
        answer=response.answer,
        query=response.query,
        sources=[SourceCitation(**s) for s in response.sources],
        results_count=response.results_count,
        retrieval_scores=response.retrieval_scores,
        model=response.model,
        intent=response.intent,
        hops=getattr(response, "hops", 0),
        session_id=req.session_id,
        error=response.error,
    )


def _build_stream(
    query: str,
    filters_dict: dict | None,
    top_k: int,
    user,
    model: str,
    session_id: str | None = None,
) -> tuple[Iterator[str] | None, list[dict]]:
    """
    Run the full RAG pipeline in a thread-pool thread.
    Identical debug output to the non-stream /chat endpoint.
    """
    from app.rag.retriever.retriever import search
    from app.rag.retriever.query_parser import detect_query_intent
    from app.rag.llm.context_builder import build_context, get_source_summary
    from app.rag.llm.prompt_builder import build_system_prompt, build_user_prompt
    from app.rag.llm.llm_client import chat as llm_chat, is_ollama_running
    from app.rag.llm.conversation_memory import memory as conv_memory

    if not is_ollama_running():
        print("[STREAM] Ollama not running")
        return None, []

    intent = detect_query_intent(query)
    print(f"[STREAM] Query={query!r}  Intent={intent}")

    effective_top_k = top_k * 4 if intent == "list" else top_k
    results = search(query=query, filters=filters_dict, top_k=effective_top_k, user=user)
    if not results:
        print("[STREAM] No results found")
        return None, []

    print(f"[STREAM] {len(results)} chunks retrieved")

    context = build_context(results, query)
    system_prompt = build_system_prompt(results=results, intent=intent)
    base_prompt   = build_user_prompt(query=query, context=context)

    history_block = conv_memory.get_context_block(session_id) if session_id else ""
    user_prompt   = f"{history_block}\n{base_prompt}" if history_block else base_prompt

    print("─" * 60)
    print(f"[STREAM PROMPT system]\n{system_prompt}\n")
    print(f"[STREAM PROMPT user]\n{user_prompt}\n")
    print("─" * 60)
    print(f"[STREAM] Starting token stream via {model}…")

    token_iter = llm_chat(
        prompt=user_prompt,
        system=system_prompt,
        model=model,
        stream=True,
    )

    sources = get_source_summary(results)
    return token_iter, sources


@router.post("/stream", summary="Streaming chat (SSE)")
async def chat_stream_endpoint(
    req: ChatRequest,
    user=Depends(get_current_user),
):
    """
    Streaming RAG + LLM answer via Server-Sent Events.

    Pipeline:
      1. `_build_stream()` runs in a thread pool (retrieval + prompt setup).
      2. `StreamingResponse(generate(), ...)` iterates the token generator;
         Starlette automatically runs sync generators in its own thread pool,
         so the event loop stays free for other requests during generation.

    Token stream format:
      data: {"type": "token",   "content": "The "}
      data: {"type": "sources", "sources": [...]}
      data: {"type": "done"}
    """
    filters_dict = {
        k: v for k, v in req.filters.model_dump().items()
        if v is not None
    } or None

    # ── Step 1: retrieval + prompt in thread (non-blocking for event loop) ──
    token_iter, sources = await asyncio.to_thread(
        _build_stream,
        req.query, filters_dict, req.top_k, user, req.model, req.session_id,
    )

    if token_iter is None:
        async def _empty():
            yield f"data: {json.dumps({'type':'error','message':'No relevant documents found or Ollama not running.'})}\n\n"
            yield f"data: {json.dumps({'type':'done'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    # ── Step 2: async generator — each token gets its own event-loop turn ──
    # Using an ASYNC generator (not sync) so Starlette does NOT wrap it in
    # iterate_in_threadpool. Instead it calls `async for chunk in gen` which
    # yields control back to the event loop (and lets Uvicorn flush the HTTP
    # chunk to the client) after EVERY token, giving a true typewriter effect.
    #
    # Each individual `next(token_iter)` still runs in a thread (blocking
    # Ollama call) via asyncio.to_thread so the event loop is never blocked.

    def _next_token(it: Iterator) -> str | None:
        try:
            return next(it)
        except StopIteration:
            return None

    async def generate():
        try:
            while True:
                token = await asyncio.to_thread(_next_token, token_iter)
                if token is None:
                    break
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection":  "keep-alive",
        },
    )


@router.post("/async", summary="Non-blocking async chat via Celery worker")
async def chat_async_endpoint(
    req: ChatRequest,
    user=Depends(get_current_user),
):
    """
    Submit a RAG query to the Celery worker queue and return immediately
    with a task_id.  Poll GET /chat/result/{task_id} for the answer.

    This endpoint never blocks the FastAPI event loop — the 100-500s LLM
    call happens entirely in the worker process.

    Workflow:
      POST /chat/async  → { "task_id": "abc123", "status": "queued" }
      GET  /chat/result/abc123 → 202 (still running) | 200 (done)
    """
    from app.workers.ocr_tasks import run_rag_query
    filters_dict = {
        k: v for k, v in req.filters.model_dump().items() if v is not None
    } or None

    task = run_rag_query.delay(
        query=req.query,
        filters=filters_dict,
        user_id=user.id,
        session_id=req.session_id,
        model=req.model,
        top_k=req.top_k,
    )
    return {"task_id": task.id, "status": "queued"}


@router.get("/result/{task_id}", summary="Poll async chat result")
async def chat_result_endpoint(
    task_id: str,
    user=Depends(get_current_user),  # noqa: ARG001 — auth guard
):
    """
    Poll for the result of a previously queued async chat task.

    Returns:
      202 { "status": "pending" }        — still running
      200 { "status": "ok", answer, … }  — complete
      200 { "status": "error", error }   — failed
    """
    from celery.result import AsyncResult
    from app.core.queue import celery_app as _app
    r = AsyncResult(task_id, app=_app)

    if r.state in ("PENDING", "STARTED", "RETRY"):
        from fastapi import Response
        return Response(
            content='{"status":"pending"}',
            status_code=202,
            media_type="application/json",
        )

    result = r.result or {}
    if r.state == "FAILURE":
        result = {"status": "error", "error": str(r.result)}

    return result


@router.delete("/session/{session_id}", summary="Clear conversation history")
async def clear_session(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: ARG001 — auth guard only
):
    """
    Delete all conversation history for a session_id.
    Call this when the user clicks 'New Chat'.
    """
    from app.rag.llm.conversation_memory import memory as conv_memory
    conv_memory.clear(session_id)
    return {"cleared": True, "session_id": session_id}


@router.get("/health", summary="Check Ollama status")
async def health_check():
    """Returns Ollama status and available models."""
    from app.rag.llm.llm_client import is_ollama_running, list_models
    running = is_ollama_running()
    return {
        "ollama_running": running,
        "models": list_models() if running else [],
        "status": "ok" if running else "ollama_not_running",
    }