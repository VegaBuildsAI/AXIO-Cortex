"""
AXIO database helpers for the optional Postgres memory backend.
"""

from __future__ import annotations

from contextlib import contextmanager

from .config import (
    AXIO_DB_HOST,
    AXIO_DB_NAME,
    AXIO_DB_PASSWORD,
    AXIO_DB_PORT,
    AXIO_DB_USER,
)


class DatabaseDependencyError(RuntimeError):
    """Raised when the optional Postgres dependency is not installed."""


def get_database_dsn() -> str:
    return (
        f"host={AXIO_DB_HOST} "
        f"port={AXIO_DB_PORT} "
        f"dbname={AXIO_DB_NAME} "
        f"user={AXIO_DB_USER} "
        f"password={AXIO_DB_PASSWORD}"
    )


def _load_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg, dict_row
    except ImportError as exc:
        raise DatabaseDependencyError(
            "Postgres backend requires psycopg. Install with: "
            "py -m pip install psycopg[binary]"
        ) from exc


def _register_vector(conn):
    """Register the pgvector type adapters on this connection.

    Without this, psycopg adapts a Python list to a Postgres array literal
    ('{...}'), which cannot be stored in or compared against a `vector`
    column -- every embedding store/recall would fail at runtime.
    """
    try:
        from pgvector.psycopg import register_vector
    except ImportError as exc:
        raise DatabaseDependencyError(
            "Postgres backend requires pgvector. Install with: "
            "py -m pip install pgvector"
        ) from exc
    register_vector(conn)


@contextmanager
def connect():
    psycopg, dict_row = _load_psycopg()
    with psycopg.connect(get_database_dsn(), row_factory=dict_row) as conn:
        _register_vector(conn)
        yield conn
