from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, Index
from sqlalchemy.sql import func
from app.core.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)

    # FILE INFO
    file_name = Column(String)
    minio_path = Column(String)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)

    # STRUCTURE
    hq_id = Column(Integer)
    unit_id = Column(Integer)
    branch_id = Column(Integer)

    document_type_id = Column(Integer)

    # UPLOAD
    uploaded_by = Column(Integer)

    # APPROVAL
    is_approved = Column(Boolean, default=False)
    approved_by = Column(Integer, nullable=True)
    rejected_by = Column(Integer, nullable=True)
    rejection_reason = Column(String, nullable=True)

    # VISIBILITY
    min_visible_rank = Column(Integer, default=6)

    # OCR WORKFLOW
    status = Column(String, default="uploaded")
    ocr_text = Column(Text, nullable=True)
    corrected_text = Column(Text, nullable=True)

    # TIMESTAMPS
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_branch", "branch_id"),
        Index("idx_type", "document_type_id"),
    )