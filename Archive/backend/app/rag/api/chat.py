from __future__ import annotations
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.rag.llm.qa_pipeline import ask, retrieve_only, QAResponse
from app.core.auth import get_current_user   # your existing auth dependency

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    query:   str          = Field(..., min_length=1, max_length=1000)
    filters: Filters      = Field(default_factory=Filters)
    top_k:   int          = Field(default=5, ge=1, le=20)
    model:   str          = Field(default="llama3:latest")
    stream:  bool         = Field(default=False)


class SourceCitation(BaseModel):
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
    error:            Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", response_model=ChatResponse, summary="Non-streaming chat")
async def chat_endpoint(
    req: ChatRequest,
    user=Depends(get_current_user),
):
    """
    Full RAG + LLM answer.

    Returns a complete ChatResponse once the LLM has finished generating.
    Use this for standard API consumption.

    On error (Ollama down, no results):
    - HTTP 503 if Ollama is unreachable
    - HTTP 200 with empty sources if no documents match the query
    """
    # Convert Pydantic Filters → plain dict (drop None values)
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
        error=response.error,
    )


@router.post("/stream", summary="Streaming chat (SSE)")
async def chat_stream_endpoint(
    req: ChatRequest,
    user=Depends(get_current_user),
):
    """
    Streaming RAG + LLM answer via Server-Sent Events.

    Token stream format:
      data: {"type": "token",  "content": "The "}
      data: {"type": "token",  "content": "command "}
      ...
      data: {"type": "sources","sources": [...]}
      data: {"type": "done"}

    Frontend pattern:
      const es = new EventSource('/api/chat/stream', {method:'POST', body:...})
      es.onmessage = (e) => {
        const msg = JSON.parse(e.data)
        if (msg.type === 'token')   appendToken(msg.content)
        if (msg.type === 'sources') renderSources(msg.sources)
        if (msg.type === 'done')    es.close()
      }
    """
    filters_dict = {
        k: v for k, v in req.filters.model_dump().items()
        if v is not None
    } or None

    # Retrieve sources synchronously FIRST so we can emit them after the stream
    results = retrieve_only(
        query=req.query,
        filters=filters_dict,
        top_k=req.top_k,
        user=user,
    )

    if not results:
        async def empty():
            yield f"data: {json.dumps({'type':'error','message':'No relevant documents found.'})}\n\n"
            yield f"data: {json.dumps({'type':'done'})}\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    # Start streaming tokens
    token_iter = ask(
        query=req.query,
        filters=filters_dict,
        top_k=req.top_k,
        user=user,
        model=req.model,
        stream=True,
    )

    from app.rag.llm.context_builder import get_source_summary

    def generate():
        for token in token_iter:
            payload = json.dumps({"type": "token", "content": token})
            yield f"data: {payload}\n\n"

        # After all tokens, emit sources
        sources = get_source_summary(results)
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


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