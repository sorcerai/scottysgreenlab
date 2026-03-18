#!/usr/bin/env python3
"""
GEO Content Engine — Brain Database Setup

Connects to Ghost PostgreSQL, executes schema.sql to create tables,
and initialises the active embedding generation record.

Usage:
  python3 scripts/brain/setup.py
"""

import sys
from pathlib import Path

import psycopg2

# ---------------------------------------------------------------------------
# Resolve config import — allow running from repo root or scripts/brain/
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import DB_URL, ACTIVE_MODEL, get_model_config

SCHEMA_PATH = SCRIPT_DIR / "schema.sql"


def main():
    if not SCHEMA_PATH.exists():
        print(f"ERROR: schema.sql not found at {SCHEMA_PATH}")
        sys.exit(1)

    model_cfg = get_model_config()
    model_dim = model_cfg["dim"]

    print("GEO Content Engine — Brain Setup")
    print(f"  Database : {DB_URL.split('@')[-1] if '@' in DB_URL else '(local)'}")
    print(f"  Model    : {ACTIVE_MODEL} ({model_dim}-dim)")
    print()

    # -----------------------------------------------------------------------
    # Connect & execute schema
    # -----------------------------------------------------------------------
    try:
        conn = psycopg2.connect(DB_URL, sslmode="require")
        conn.autocommit = True
        cur = conn.cursor()
    except Exception as e:
        print(f"ERROR: Could not connect to database — {e}")
        sys.exit(1)

    print("Executing schema.sql ...")
    schema_sql = SCHEMA_PATH.read_text()

    # Execute each statement individually so IF NOT EXISTS works cleanly
    # Split on semicolons that are followed by a newline (crude but effective
    # for our well-structured schema file).
    statements = [s.strip() for s in schema_sql.split(";\n") if s.strip()]
    for stmt in statements:
        if not stmt:
            continue
        try:
            cur.execute(stmt)
        except psycopg2.errors.DuplicateObject:
            # Index or constraint already exists — harmless
            conn.rollback() if not conn.autocommit else None
        except Exception as e:
            print(f"  WARNING: {e}")
            conn.rollback() if not conn.autocommit else None

    print("  Schema applied successfully.")

    # -----------------------------------------------------------------------
    # Create initial embedding generation record
    # -----------------------------------------------------------------------
    print(f"Registering embedding model: {ACTIVE_MODEL} ...")
    cur.execute(
        """
        INSERT INTO brain_embedding_generations (model_name, model_dim, is_active)
        VALUES (%s, %s, true)
        ON CONFLICT (model_name) DO UPDATE SET
            model_dim = EXCLUDED.model_dim,
            is_active = true
        RETURNING id
        """,
        (ACTIVE_MODEL, model_dim),
    )
    gen_id = cur.fetchone()[0]

    # Deactivate other models
    cur.execute(
        "UPDATE brain_embedding_generations SET is_active = false WHERE model_name != %s",
        (ACTIVE_MODEL,),
    )
    print(f"  Generation ID: {gen_id} (active)")

    # -----------------------------------------------------------------------
    # Report table counts
    # -----------------------------------------------------------------------
    print()
    print("Table status:")
    tables = [
        "brain_documents",
        "brain_embeddings",
        "brain_embedding_generations",
        "brain_sources",
        "brain_entities",
        "brain_entity_relationships",
    ]
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table:35s} {count:>6} rows")
        except Exception:
            print(f"  {table:35s}  (not found)")
            conn.rollback() if not conn.autocommit else None

    conn.close()
    print()
    print("Setup complete.")


if __name__ == "__main__":
    main()
