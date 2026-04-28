"""
One-time migration: add the `keywords` column to the documents table.

Run from Archive/backend/:
    python scripts/add_keywords_column.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import engine
from sqlalchemy import text

SQL = "ALTER TABLE documents ADD COLUMN IF NOT EXISTS keywords TEXT;"

with engine.connect() as conn:
    conn.execute(text(SQL))
    conn.commit()
    print("✅ Column 'keywords' added to documents table (or already existed).")
