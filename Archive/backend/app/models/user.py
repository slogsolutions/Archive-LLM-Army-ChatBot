from sqlalchemy import Column, Integer, String
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
    password = Column(String)

    role = Column(String)
    rank_level = Column(Integer)

    # RELATIONS
    hq_id = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)
    branch_id = Column(Integer, nullable=True)

    task_category = Column(String, nullable=True)