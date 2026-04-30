"""
Hardware & Worker Configuration
================================
**Single place to control everything.**

Edit this file (or set the matching environment variables in .env) to:
  - Switch between GPU / CPU
  - Tune worker concurrency and inter-document delay
  - Control memory limits
  - Tune batch sizes

Environment variables always win over the defaults below.

GTX 1660 Ti reference (6 GB VRAM):
  - Marker OCR during indexing  : ~2-3 GB
  - Embedding model at runtime  : ~0.4 GB
  - Cross-encoder at runtime    : ~0.1 GB
  → Total if Marker is unloaded before serving: ~0.5 GB idle, ~3 GB peak (OCR)
  → MARKER_UNLOAD_AFTER_USE = True is REQUIRED for 6 GB cards

Change log:
  - Set WORKER_CONCURRENCY=2 only when you have >= 12 GB RAM
  - Set MARKER_UNLOAD_AFTER_USE=False only when VRAM >= 8 GB
"""
from __future__ import annotations
import os


# ---------------------------------------------------------------------------
# Internal helper — called once at import time
# ---------------------------------------------------------------------------

def _detect_device() -> str:
    force = os.getenv("RAG_DEVICE", "").lower()
    if force in ("cpu", "cuda", "mps"):
        return force
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            vram_gb = props.total_memory / (1024 ** 3)
            print(
                f"[HW_CONFIG] GPU detected: {props.name}  "
                f"VRAM={vram_gb:.1f} GB  "
                f"CUDA={torch.version.cuda}"
            )
            return "cuda"
    except Exception:
        pass
    print("[HW_CONFIG] No CUDA GPU — using CPU")
    return "cpu"


# ═══════════════════════════════════════════════════════════════════════════
#  DEVICE
#  -------
#  "cuda"  → NVIDIA GPU (recommended for 1660 Ti)
#  "cpu"   → force CPU even if GPU is present
#  auto    → detected at startup (default)
# ═══════════════════════════════════════════════════════════════════════════
DEVICE: str = _detect_device()


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER / QUEUE
#  --------------
#  WORKER_CONCURRENCY        How many documents to process in parallel.
#                            ← 1 is safe for 8 GB RAM; set 2 for ≥ 12 GB
#
#  WORKER_INTER_DOC_DELAY_S  Sleep this many seconds between documents.
#                            Gives RAM/VRAM time to clear after Marker.
#                            ← Recommended: 3-5 s for 8 GB RAM
#
#  WORKER_MAX_RAM_MB         If process RSS exceeds this, skip the task and
#                            re-queue it.  0 = disabled.
#                            ← 3500 is safe for 8 GB total RAM
# ═══════════════════════════════════════════════════════════════════════════
WORKER_CONCURRENCY:        int   = int(os.getenv("WORKER_CONCURRENCY",        "1"))
WORKER_INTER_DOC_DELAY_S:  float = float(os.getenv("WORKER_INTER_DOC_DELAY_S", "5.0"))
WORKER_MAX_RAM_MB:         int   = int(os.getenv("WORKER_MAX_RAM_MB",          "3500"))


# ═══════════════════════════════════════════════════════════════════════════
#  MARKER OCR
#  ----------
#  MARKER_DEVICE           Device Marker runs its layout + OCR models on.
#  MARKER_BATCH_MULT       Batch multiplier; higher = faster but more VRAM.
#                          ← GPU: 2, CPU: 1
#  MARKER_UNLOAD_AFTER_USE Unload Marker PyTorch models from VRAM after
#                          each document.  MUST be True for 6 GB cards.
# ═══════════════════════════════════════════════════════════════════════════
MARKER_DEVICE:           str  = os.getenv("MARKER_DEVICE",           DEVICE)
MARKER_BATCH_MULT:       int  = int(os.getenv("MARKER_BATCH_MULT",  "2" if DEVICE == "cuda" else "1"))
MARKER_UNLOAD_AFTER_USE: bool = os.getenv("MARKER_UNLOAD_AFTER_USE", "true").lower() != "false"


# ═══════════════════════════════════════════════════════════════════════════
#  EMBEDDING MODEL
#  ---------------
#  EMBEDDING_DEVICE  Device the sentence-transformer runs on.
#  EMBEDDING_BATCH   Batch size for encoding.
#                    ← GPU: 64, CPU: 32
# ═══════════════════════════════════════════════════════════════════════════
EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", DEVICE)
EMBEDDING_BATCH:  int = int(os.getenv("EMBEDDING_BATCH", "64" if DEVICE == "cuda" else "32"))


# ═══════════════════════════════════════════════════════════════════════════
#  CROSS-ENCODER RERANKER
#  ----------------------
#  RERANKER_DEVICE  Device the cross-encoder runs on.
# ═══════════════════════════════════════════════════════════════════════════
RERANKER_DEVICE: str = os.getenv("RERANKER_DEVICE", DEVICE)


# ═══════════════════════════════════════════════════════════════════════════
#  CHUNKING  (affects quality — only change after re-indexing)
#  --------
#  CHUNK_SIZE     Words per prose sliding-window chunk (flat fallback path)
#  CHUNK_OVERLAP  Overlap between adjacent prose chunks
#  CHILD_SIZE     Words per child chunk (parent-child path)
#  CHILD_OVERLAP  Overlap between adjacent children
# ═══════════════════════════════════════════════════════════════════════════
CHUNK_SIZE:    int = int(os.getenv("CHUNK_SIZE",    "150"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "30"))
CHILD_SIZE:    int = int(os.getenv("CHILD_SIZE",    "120"))
CHILD_OVERLAP: int = int(os.getenv("CHILD_OVERLAP", "20"))


# ═══════════════════════════════════════════════════════════════════════════
#  CONTEXT / RETRIEVAL
#  -------------------
#  MAX_CONTEXT_CHARS  Maximum chars of context sent to the LLM
#  MAX_PROSE_CHARS    Maximum chars shown per prose chunk in context
#  TOP_K_DEFAULT      Default number of chunks to retrieve per query
# ═══════════════════════════════════════════════════════════════════════════
MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))
MAX_PROSE_CHARS:   int = int(os.getenv("MAX_PROSE_CHARS",   "1200"))
TOP_K_DEFAULT:     int = int(os.getenv("TOP_K_DEFAULT",     "5"))


def print_summary() -> None:
    """Print the active hardware configuration at startup."""
    print("=" * 56)
    print("  RAG Hardware Configuration")
    print("=" * 56)
    print(f"  Device              : {DEVICE.upper()}")
    print(f"  Marker device       : {MARKER_DEVICE.upper()}")
    print(f"  Marker batch mult   : {MARKER_BATCH_MULT}")
    print(f"  Marker unload VRAM  : {MARKER_UNLOAD_AFTER_USE}")
    print(f"  Embedding device    : {EMBEDDING_DEVICE.upper()}")
    print(f"  Embedding batch     : {EMBEDDING_BATCH}")
    print(f"  Reranker device     : {RERANKER_DEVICE.upper()}")
    print(f"  Worker concurrency  : {WORKER_CONCURRENCY}")
    print(f"  Inter-doc delay     : {WORKER_INTER_DOC_DELAY_S} s")
    print(f"  Max RAM guard       : {WORKER_MAX_RAM_MB} MB (0=off)")
    print(f"  Chunk size          : {CHUNK_SIZE} words")
    print(f"  Child size          : {CHILD_SIZE} words")
    print("=" * 56)
