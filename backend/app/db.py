"""Database connection and lightweight dev schema fixes."""

from fastapi import status as http_status
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.errors import AppError

_engine = None
_SessionLocal = None


def init_engine(db_url: str, echo: bool = False) -> None:
    global _engine, _SessionLocal
    _engine = create_engine(db_url, echo=echo)
    _apply_startup_schema_fixes(_engine)
    _SessionLocal = sessionmaker(bind=_engine)


def _apply_startup_schema_fixes(engine) -> None:
    """Patch older local SQLite schemas so current routes can query them."""
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "sdf_molecules" not in existing_tables and "candidate_molecules" not in existing_tables:
        return

    table_missing_columns: dict[str, dict[str, str]] = {
        "sdf_molecules": {
            "sa_score": "FLOAT",
        },
        "candidate_molecules": {
            "standard_name": "VARCHAR(255)",
        },
        "targets": {
            "name": "VARCHAR(255)",
            "status": "VARCHAR(20) DEFAULT 'created'",
        },
    }

    with engine.begin() as connection:
        for table_name, missing_columns in table_missing_columns.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in missing_columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))


def get_engine():
    return _engine


def get_sessionmaker() -> sessionmaker:
    return _SessionLocal


def get_db():
    """Create one session per request and close it automatically."""
    if _SessionLocal is None:
        raise AppError(
            message="Database not connected",
            code="DATABASE_NOT_CONNECTED",
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    db = _SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
