"""
RAG Logs API — audit trail + monitoring for military deployments.

Endpoints
---------
GET  /logs/rag          paginated query log with filters
GET  /logs/rag/summary  aggregate stats (last 24h, 7d, 30d)
GET  /logs/embedding    embedding cache stats
GET  /logs/audit        existing audit log (user actions)
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.core.deps import get_current_user, get_db
from app.models.rag_log   import RAGLog
from app.models.audit_logs import AuditLog

router = APIRouter()


# ── helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user):
    if user.role not in ["super_admin", "hq_admin", "unit_admin", "officer"]:
        from fastapi import HTTPException
        raise HTTPException(403, "Insufficient permissions")


# ── RAG query log ─────────────────────────────────────────────────────────────

@router.get("/rag")
def list_rag_logs(
    page:       int            = Query(1,  ge=1),
    per_page:   int            = Query(50, ge=1, le=200),
    status:     Optional[str]  = Query(None),
    intent:     Optional[str]  = Query(None),
    min_conf:   Optional[float] = Query(None),
    max_conf:   Optional[float] = Query(None),
    days:       int            = Query(7, ge=1, le=90),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Paginated list of RAG query logs.
    Filterable by status, intent, confidence range, and time window.
    """
    _require_admin(user)

    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(RAGLog).filter(RAGLog.created_at >= since)

    if status:
        q = q.filter(RAGLog.status == status)
    if intent:
        q = q.filter(RAGLog.intent == intent)
    if min_conf is not None:
        q = q.filter(RAGLog.confidence >= min_conf)
    if max_conf is not None:
        q = q.filter(RAGLog.confidence <= max_conf)

    total = q.count()
    rows  = (
        q.order_by(desc(RAGLog.created_at))
         .offset((page - 1) * per_page)
         .limit(per_page)
         .all()
    )

    return {
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "items": [
            {
                "id":              r.id,
                "query":           r.query,
                "intent":          r.intent,
                "status":          r.status,
                "confidence":      r.confidence,
                "faithfulness":    r.faithfulness,
                "keyword_coverage": r.keyword_coverage,
                "retrieval_count": r.retrieval_count,
                "unique_sources":  r.unique_sources,
                "top_score":       r.top_score,
                "answer_preview":  r.answer_preview,
                "answer_length":   r.answer_length,
                "latency_s":       r.latency_s,
                "model":           r.model,
                "was_rejected":    r.was_rejected,
                "created_at":      r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/rag/summary")
def rag_log_summary(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Aggregate stats for the dashboard cards."""
    _require_admin(user)

    def _stats(days: int):
        since = datetime.utcnow() - timedelta(days=days)
        rows = db.query(RAGLog).filter(RAGLog.created_at >= since).all()
        if not rows:
            return {"total": 0}
        latencies   = [r.latency_s   for r in rows if r.latency_s   is not None]
        confs       = [r.confidence  for r in rows if r.confidence  is not None]
        return {
            "total":           len(rows),
            "rejected":        sum(1 for r in rows if r.was_rejected),
            "not_found":       sum(1 for r in rows if r.status == "not_found"),
            "avg_latency_s":   round(sum(latencies) / len(latencies), 1) if latencies else None,
            "avg_confidence":  round(sum(confs) / len(confs), 3)         if confs      else None,
            "intents": {
                "prose":   sum(1 for r in rows if r.intent == "prose"),
                "list":    sum(1 for r in rows if r.intent == "list"),
                "command": sum(1 for r in rows if r.intent == "command"),
                "mixed":   sum(1 for r in rows if r.intent == "mixed"),
            },
        }

    return {
        "last_24h": _stats(1),
        "last_7d":  _stats(7),
        "last_30d": _stats(30),
    }


# ── Embedding cache stats ─────────────────────────────────────────────────────

@router.get("/embedding-cache")
def embedding_cache_stats(user=Depends(get_current_user)):
    _require_admin(user)
    from app.rag.embedding.cache import cache_stats
    return cache_stats()


# ── Audit log ─────────────────────────────────────────────────────────────────

@router.get("/audit")
def list_audit_logs(
    page:     int           = Query(1, ge=1),
    per_page: int           = Query(50, ge=1, le=200),
    action:   Optional[str] = Query(None),
    days:     int           = Query(7, ge=1, le=90),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)

    since = datetime.utcnow() - timedelta(days=days)
    q = db.query(AuditLog).filter(AuditLog.timestamp >= since)
    if action:
        q = q.filter(AuditLog.action == action)

    total = q.count()
    rows  = (
        q.order_by(desc(AuditLog.timestamp))
         .offset((page - 1) * per_page)
         .limit(per_page)
         .all()
    )
    return {
        "total": total, "page": page, "per_page": per_page,
        "items": [
            {
                "id":          r.id,
                "action":      r.action,
                "user_id":     r.user_id,
                "role":        r.role,
                "target_id":   r.target_id,
                "target_type": r.target_type,
                "status":      r.status,
                "message":     r.message,
                "timestamp":   r.timestamp.isoformat() if r.timestamp else None,
            }
            for r in rows
        ],
    }
