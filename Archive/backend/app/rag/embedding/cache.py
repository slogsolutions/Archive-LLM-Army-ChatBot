"""
Redis Embedding Cache — reduces per-query embedding cost.

On CPU, embedding one query takes ~0.5-2 seconds.  The same query
(or a very similar one) is often asked repeatedly in a training context.
This cache stores embeddings by MD5(text) with a 2-hour TTL.

Impact:
  - Cache hit  → 0 ms embedding (skip model entirely)
  - Cache miss → normal 0.5-2 s embedding, then cached for 2 hours
  - Typical hit rate in practice: 20-40% for training environments

Integration: imported by embedder.py — no other change needed.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import List, Optional

_REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
_TTL_SECONDS = 7200   # 2 hours
_KEY_PREFIX  = "emb:"

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.from_url(_REDIS_URL, decode_responses=False)
            _redis_client.ping()
        except Exception as e:
            print(f"[EMB_CACHE] Redis unavailable ({e}) — cache disabled")
            _redis_client = False   # sentinel: don't retry
    return _redis_client if _redis_client else None


def _key(text: str) -> str:
    return _KEY_PREFIX + hashlib.md5(text.encode("utf-8")).hexdigest()


def get_cached(text: str) -> Optional[List[float]]:
    """Return cached embedding vector or None on miss / unavailable."""
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_key(text))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def set_cached(text: str, embedding: List[float]) -> None:
    """Store embedding in Redis with TTL.  Silently swallows errors."""
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(_key(text), _TTL_SECONDS, json.dumps(embedding))
    except Exception:
        pass


def cache_stats() -> dict:
    """Return approximate cache stats (key count, memory).  Best-effort."""
    r = _get_redis()
    if r is None:
        return {"status": "disabled"}
    try:
        keys = r.keys(f"{_KEY_PREFIX}*")
        info = r.info("memory")
        return {
            "status": "ok",
            "cached_embeddings": len(keys),
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
