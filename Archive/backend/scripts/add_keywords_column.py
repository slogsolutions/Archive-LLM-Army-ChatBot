"""
One-time migration: add `keywords` column to both documents AND document_chunks.

Run from Archive/backend/:
    python scripts/add_keywords_column.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import engine
from sqlalchemy import text

STATEMENTS = [
    "ALTER TABLE documents       ADD COLUMN IF NOT EXISTS keywords TEXT;",
    "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS keywords TEXT;",
]

with engine.connect() as conn:
    for sql in STATEMENTS:
        conn.execute(text(sql))
        print(f"✅ {sql}")
    conn.commit()

print("✅ All migrations applied.")
