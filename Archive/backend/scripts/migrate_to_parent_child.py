"""
Batch Migration: Flat chunks → Parent-Child structure
=====================================================

Re-index all approved documents already in the database using the new
parent-child ingestion pipeline (ingest_document_v2).

Strategy
--------
For each document with status="indexed":
  1. Download original PDF from MinIO
  2. Run md_parser (Marker → Docling → PyMuPDF → PaddleOCR)
  3. chunk_into_parent_child() → parents + children
  4. Embed children, delete old ES docs, index parents + children

The old flat chunks are REPLACED.  Documents that fail are left in their
current state and logged to migration_errors.txt.

Usage
-----
# Dry run — show what would be migrated
python scripts/migrate_to_parent_child.py --dry-run

# Migrate all indexed documents
python scripts/migrate_to_parent_child.py

# Migrate specific doc IDs
python scripts/migrate_to_parent_child.py --doc-ids 9 10 11

# Migrate documents from a specific branch
python scripts/migrate_to_parent_child.py --branch "G"
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback

# ── Path setup ────────────────────────────────────────────────────────────────
_backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _backend)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def _get_docs(doc_ids=None, branch=None):
    from app.core.database import SessionLocal
    from app.models.document import Document

    db = SessionLocal()
    try:
        q = db.query(Document).filter(
            Document.is_deleted == False,
            Document.is_approved == True,
            Document.status.in_(["indexed", "processed", "reviewed"]),
        )
        if doc_ids:
            q = q.filter(Document.id.in_(doc_ids))
        if branch:
            q = q.filter(Document.branch_name == branch)
        return q.order_by(Document.id).all()
    finally:
        db.close()


def _migrate_one(doc_id: int, dry_run: bool) -> dict:
    from app.core.database import SessionLocal
    from app.models.document import Document
    from app.rag.pipeline import ingest_document_v2

    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if not doc:
            return {"doc_id": doc_id, "status": "skip", "reason": "not found"}

        print(f"\n[MIGRATE] doc_id={doc_id}  file={doc.file_name[:60]}")

        if dry_run:
            has_text = bool(doc.corrected_text or doc.ocr_text)
            has_pdf  = bool(doc.minio_path)
            print(f"[MIGRATE] DRY-RUN — has_pdf={has_pdf} has_text={has_text}")
            return {"doc_id": doc_id, "status": "dry_run"}

        t0     = time.time()
        n      = ingest_document_v2(doc)
        elapsed = round(time.time() - t0, 1)

        print(f"[MIGRATE] ✅ doc_id={doc_id}: {n} children indexed in {elapsed}s")
        return {"doc_id": doc_id, "status": "ok", "children": n, "elapsed_s": elapsed}

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[MIGRATE] ❌ doc_id={doc_id}: {e}")
        return {"doc_id": doc_id, "status": "error", "error": str(e), "tb": tb}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate flat chunks to parent-child RAG")
    parser.add_argument("--doc-ids",  nargs="+", type=int, default=None)
    parser.add_argument("--branch",   type=str,  default=None)
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--pause",    type=float, default=2.0,
                        help="Seconds to pause between documents (avoids overloading Ollama)")
    args = parser.parse_args()

    docs = _get_docs(args.doc_ids, args.branch)
    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Migrating {len(docs)} document(s)…\n")

    results = []
    for i, doc in enumerate(docs, 1):
        print(f"── {i}/{len(docs)} ──────────────────────────────────────────")
        r = _migrate_one(doc.id, dry_run=args.dry_run)
        results.append(r)

        if not args.dry_run and i < len(docs):
            time.sleep(args.pause)   # let the embedding model cool down

    # ── Summary ──────────────────────────────────────────────────────────
    ok     = [r for r in results if r["status"] == "ok"]
    errors = [r for r in results if r["status"] == "error"]
    dry    = [r for r in results if r["status"] == "dry_run"]

    print("\n" + "═" * 60)
    print(f"  MIGRATION COMPLETE")
    print(f"  OK:      {len(ok)}")
    print(f"  Errors:  {len(errors)}")
    print(f"  Dry-run: {len(dry)}")
    if ok:
        total_children = sum(r.get("children", 0) for r in ok)
        avg_t = sum(r.get("elapsed_s", 0) for r in ok) / len(ok)
        print(f"  Total children indexed : {total_children}")
        print(f"  Avg time per doc       : {avg_t:.1f}s")
    print("═" * 60)

    # Write error log
    if errors:
        log_path = os.path.join(_backend, "migration_errors.txt")
        with open(log_path, "w") as f:
            for e in errors:
                f.write(f"doc_id={e['doc_id']}\n{e.get('tb','')}\n---\n")
        print(f"\nError details written to: {log_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
