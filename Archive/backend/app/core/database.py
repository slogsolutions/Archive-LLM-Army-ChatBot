# config/dbConfig

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://archive_admin:StrongPass123@localhost:5432/archive_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()