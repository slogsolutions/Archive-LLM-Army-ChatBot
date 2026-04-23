from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)

    action = Column(String, nullable=False)

    user_id = Column(Integer)
    role = Column(String)

    target_id = Column(Integer, nullable=True)  # doc_id etc
    target_type = Column(String, nullable=True)  # "document"

    status = Column(String)  # SUCCESS / FAILED

    message = Column(String, nullable=True)

    extra = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)