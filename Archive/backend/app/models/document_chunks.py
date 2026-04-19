from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)

    document_id = Column(Integer, ForeignKey("documents.id"))

    chunk_text = Column(Text, nullable=False)

    # metadata (important for filtering)
    section = Column(String, nullable=True)
    page = Column(Integer, nullable=True)

    # optional (for future DB vector)
    # embedding = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_doc", "document_id"),
    )