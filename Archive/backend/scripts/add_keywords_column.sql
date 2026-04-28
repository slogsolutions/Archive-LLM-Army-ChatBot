-- Add keywords column to existing documents and document_chunks tables.
-- Run this once against your PostgreSQL database if you are NOT using
-- alembic autogenerate (i.e. the tables already exist without the column).

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS keywords TEXT;

ALTER TABLE document_chunks
  ADD COLUMN IF NOT EXISTS keywords TEXT;
