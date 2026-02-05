# database.py
"""
SQLAlchemy database connection and session management.

This module provides:
- Database engine configuration for Azure SQL (MS SQL Server)
- Session factory for dependency injection
- Connection utilities

Usage:
     from database import get_session, engine
     
     # In FastAPI routes:
     @app.get("/items")
     def get_items(db: Session = Depends(get_session)):
          return db.query(Item).all()
     """
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration from environment
DB_SERVER = os.getenv("DB_SERVER")
DB_PORT = os.getenv("DB_PORT", "1433")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

# Build connection string for MS SQL Server using pymssql
# Format: mssql+pymssql://user:password@server:port/database
DATABASE_URL = (
     f"mssql+pymssql://{DB_USER}:{DB_PASS}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"
)

# Create SQLAlchemy engine
engine = create_engine(
     DATABASE_URL,
     poolclass=QueuePool,
     pool_size=5,
     max_overflow=10,
     pool_timeout=30,
     pool_recycle=1800,  # Recycle connections after 30 minutes
     echo=os.getenv("SQL_ECHO", "false").lower() == "true",  # Log SQL if SQL_ECHO=true
)

# Session factory
SessionLocal = sessionmaker(
     bind=engine,
     autocommit=False,
     autoflush=False,
     expire_on_commit=False,
)


def get_session() -> Generator[Session, None, None]:
     """
     FastAPI dependency that provides a database session.
     
     Usage:
          @app.get("/items")
          def get_items(db: Session = Depends(get_session)):
               return db.query(Item).all()
     
     Yields:
          Session: SQLAlchemy database session
     """
     session = SessionLocal()
     try:
          yield session
          session.commit()
     except Exception:
          session.rollback()
          raise
     finally:
          session.close()


@contextmanager
def get_session_context() -> Generator[Session, None, None]:
     """
     Context manager for database sessions (for use outside FastAPI routes).
     
     Usage:
          with get_session_context() as db:
               users = db.query(User).all()
     
     Yields:
          Session: SQLAlchemy database session
     """
     session = SessionLocal()
     try:
          yield session
          session.commit()
     except Exception:
          session.rollback()
          raise
     finally:
          session.close()


def init_db() -> None:
     """
     Initialize database tables.
     
     Creates all tables defined in the models if they don't exist.
     For production, use Alembic migrations instead.
     """
     from models import Base
     Base.metadata.create_all(bind=engine)


def check_connection() -> bool:
     """
     Test database connectivity.
     
     Returns:
          bool: True if connection successful, False otherwise
     """
     try:
          with engine.connect() as conn:
               conn.execute("SELECT 1")
          return True
     except Exception as e:
          print(f"Database connection failed: {e}")
          return False
