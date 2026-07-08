
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import (
    DeclarativeBase,
    sessionmaker,
)


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
database_password = os.getenv("DATABASE_PASSWORD") or ""

DATABASE_URL = f"postgresql://postgres:{database_password}@localhost:5432/osipress"
engine = create_engine(DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(bind=engine)