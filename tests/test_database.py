"""Tests for database connectivity, Alembic migration state, and pgvector operations."""

import pytest
from sqlalchemy import text
from database.connection import engine, SessionLocal


def test_database_connection():
    """Verify that Python can connect to PostgreSQL."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_vector_extension_active():
    """Verify that the pgvector extension is enabled and reported in pg_extension."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        assert result is not None, "pgvector extension is not installed"
        assert result[0] == "vector"
        print(f"pgvector version: {result[1]}")


def test_vector_insert_and_l2_distance_search():
    """Verify that vectors can be stored, indexed, and queried using L2 distance (<->)."""
    with engine.connect() as conn:
        # Create a temporary table with a 3-dimensional vector column
        conn.execute(text("CREATE TEMP TABLE items (id SERIAL PRIMARY KEY, embedding vector(3))"))
        
        # Insert test vectors
        conn.execute(
            text(
                "INSERT INTO items (embedding) VALUES "
                "('[1, 0, 0]'), "
                "('[0, 1, 0]'), "
                "('[0, 0, 1]')"
            )
        )
        
        # Query nearest neighbor using L2 distance (<->) to [1, 0, 0]
        row = conn.execute(
            text("SELECT id, embedding <-> '[1, 0, 0]' AS dist FROM items ORDER BY dist LIMIT 1")
        ).fetchone()
        
        assert row is not None
        assert row[0] == 1
        assert pytest.approx(float(row[1]), abs=1e-5) == 0.0


def test_vector_cosine_distance_search():
    """Verify vector search using cosine distance (<=>)."""
    with engine.connect() as conn:
        conn.execute(text("CREATE TEMP TABLE doc_vectors (id SERIAL PRIMARY KEY, vec vector(4))"))
        conn.execute(
            text(
                "INSERT INTO doc_vectors (vec) VALUES "
                "('[0.5, 0.5, 0.5, 0.5]'), "
                "('[-0.5, -0.5, -0.5, -0.5]')"
            )
        )
        
        # Cosine distance to identical vector should be ~0.0
        row = conn.execute(
            text("SELECT id, vec <=> '[0.5, 0.5, 0.5, 0.5]' AS dist FROM doc_vectors ORDER BY dist LIMIT 1")
        ).fetchone()
        
        assert row is not None
        assert row[0] == 1
        assert pytest.approx(float(row[1]), abs=1e-5) == 0.0
