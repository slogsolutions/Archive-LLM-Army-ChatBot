from sqlalchemy import Column, Integer, String
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    army_number = Column(String, unique=True)
    name = Column(String)
    password = Column(String)

    role = Column(String)
    rank_level = Column(Integer)

    # RELATIONS
    hq_id = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)
    branch_id = Column(Integer, nullable=True)
    clerk_type = Column(String, nullable=True)  # values: "junior", "senior"

    task_category = Column(String, nullable=True)
