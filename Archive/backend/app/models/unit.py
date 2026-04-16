from sqlalchemy import Column, Integer, String
from app.core.database import Base

class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    hq_id = Column(Integer)  # FK later