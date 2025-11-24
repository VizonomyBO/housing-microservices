"""
Database configuration using pure SQLAlchemy
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import Config

Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db(config: Config) -> None:
    """Initialize database engine and session factory"""
    global _engine, _SessionLocal

    _engine = create_engine(
        config.SQLALCHEMY_DATABASE_URI,
        **config.SQLALCHEMY_ENGINE_OPTIONS,
    )
    _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_session() -> Session:
    """Get a database session"""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


def create_tables() -> None:
    """Create all database tables"""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    Base.metadata.create_all(bind=_engine)


def drop_tables() -> None:
    """Drop all database tables"""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    Base.metadata.drop_all(bind=_engine)
