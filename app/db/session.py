# app/db/session.py
from typing import Generator
from sqlalchemy.orm import Session
# Ajusta este import a donde tengas tu SessionLocal real
from app.db.database import SessionLocal  # p. ej.: app/db/database.py

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
