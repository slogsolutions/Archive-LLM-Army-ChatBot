from sqlalchemy import Column, Integer, String
from app.core.database import Base

class HeadQuarter(Base):
    __tablename__ = "headquarters"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)