from __future__ import annotations
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Boolean, Index
from sqlalchemy.sql import func
from app.core.database import Base


class RAGLog(Base):
    """
    Detailed trace of every RAG query — the audit trail for military use.

    One row per query execution, stored regardless of success or failure.
    Used by the logging dashboard to track:
      - Answer quality over time
      - Retrieval failures
      - Latency breakdown
      - Confidence distribution
      - Source utilisation
    """
    __tablename__ = "rag_logs"

    id               = Column(Integer, primary_key=True)

    # ── Query ────────────────────────────────────────────────────────────
    query            = Column(Text,    nullable=False)
    intent           = Column(String,  nullable=True)   # prose/list/command/mixed
    session_id       = Column(String,  nullable=True)
    user_id          = Column(Integer, nullable=True)

    # ── Retrieval ─────────────────────────────────────────────────────────
    retrieval_count  = Column(Integer, default=0)     # unique chunks after dedup
    unique_sources   = Column(Integer, default=0)     # unique document files
    top_score        = Column(Float,   nullable=True)  # highest ES score
    avg_score        = Column(Float,   nullable=True)  # mean of top-5 scores
    sources_json     = Column(Text,    nullable=True)  # JSON list of file_names

    # ── Answer ────────────────────────────────────────────────────────────
    answer_preview   = Column(Text,    nullable=True)  # first 500 chars
    answer_length    = Column(Integer, default=0)      # total chars

    # ── Quality signals ───────────────────────────────────────────────────
    confidence       = Column(Float,   nullable=True)  # 0.0 – 1.0 composite score
    faithfulness     = Column(Float,   nullable=True)  # lexical overlap
    keyword_coverage = Column(Float,   nullable=True)  # query terms in context
    was_rejected     = Column(Boolean, default=False)  # rejected by confidence gate

    # ── Status ────────────────────────────────────────────────────────────
    status = Column(String, default="ok")
    # Values: "ok" | "rejected" | "not_found" | "ollama_down" | "error"

    # ── Performance ───────────────────────────────────────────────────────
    latency_s        = Column(Float,   nullable=True)  # wall-clock seconds
    model            = Column(String,  nullable=True)  # e.g. "llama3:latest"
    method           = Column(String,  nullable=True)  # "stream" | "async" | "sync"

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_rag_log_created",    "created_at"),
        Index("idx_rag_log_user",       "user_id"),
        Index("idx_rag_log_status",     "status"),
        Index("idx_rag_log_confidence", "confidence"),
    )
