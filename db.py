import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None
_schema_ready = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    avatar_url TEXT,
    github_id TEXT UNIQUE,
    google_id TEXT UNIQUE,
    github_token TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS repos (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    github_id BIGINT,
    name VARCHAR(255),
    full_name VARCHAR(255),
    html_url TEXT,
    description TEXT,
    language VARCHAR(100),
    stars INTEGER DEFAULT 0,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (user_id, github_id)
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    repo_id INTEGER REFERENCES repos(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    branch VARCHAR(100) DEFAULT 'main',
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);
"""


def _ensure_schema(conn):
    global _schema_ready
    if _schema_ready:
        return
    try:
        cur = conn.cursor()
        cur.execute(SCHEMA)
        conn.commit()
        cur.close()
        _schema_ready = True
        print("[db] schema ensured")
    except Exception as e:
        conn.rollback()
        print(f"[db] schema creation failed: {e}")


def _get_pool():
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        _pool = ThreadedConnectionPool(1, 10, DATABASE_URL, cursor_factory=RealDictCursor)
    return _pool


@contextmanager
def get_db():
    conn = _get_pool().getconn()
    try:
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _get_pool().putconn(conn)
