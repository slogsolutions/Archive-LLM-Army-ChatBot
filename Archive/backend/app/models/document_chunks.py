from sqlalchemy import Column, Integer, String, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.core.database import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True)

    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"))

    chunk_text = Column(Text, nullable=False)

    page = Column(Integer, nullable=True)
    section = Column(String, nullable=True)

    chunk_index = Column(Integer, nullable=False)
    total_chunks = Column(Integer, nullable=True)

    heading = Column(String, nullable=True)
    char_offset = Column(Integer, nullable=True)

    # optional future (pgvector)
    embedding = Column(Text, nullable=True)

    document = relationship("Document", backref="chunks")

    __table_args__ = (
        Index("idx_doc", "document_id"),
        Index("idx_page", "page"),
    )