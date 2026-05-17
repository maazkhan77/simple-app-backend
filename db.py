import os
import re
from contextlib import contextmanager
from urllib.parse import urlparse

import requests

DATABASE_URL = os.getenv("DATABASE_URL")

_endpoint_url = None
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


SCHEMA_STATEMENTS = [s.strip() for s in SCHEMA.split(";") if s.strip()]


def _get_endpoint():
    global _endpoint_url
    if _endpoint_url is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is not set")
        parsed = urlparse(DATABASE_URL)
        if not parsed.hostname:
            raise RuntimeError("DATABASE_URL has no hostname")
        _endpoint_url = f"https://{parsed.hostname}/sql"
    return _endpoint_url


def _translate_placeholders(query: str) -> str:
    counter = [0]

    def repl(_m):
        counter[0] += 1
        return f"${counter[0]}"

    return re.sub(r"%s", repl, query)


def _execute(query: str, params=()):
    url = _get_endpoint()
    translated = _translate_placeholders(query)
    body = {"query": translated, "params": list(params or [])}
    headers = {
        "Neon-Connection-String": DATABASE_URL,
        "Content-Type": "application/json",
    }
    r = requests.post(url, json=body, headers=headers, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Neon HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data.get("rows", []) or []


def _ensure_schema():
    global _schema_ready
    if _schema_ready:
        return
    try:
        for stmt in SCHEMA_STATEMENTS:
            _execute(stmt)
        _schema_ready = True
        print("[db] schema ensured")
    except Exception as e:
        print(f"[db] schema creation failed: {e}")


class _Cursor:
    def __init__(self):
        self._rows = []
        self._idx = 0

    def execute(self, query, params=()):
        self._rows = _execute(query, params)
        self._idx = 0

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self):
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows

    def close(self):
        pass


class _Connection:
    def cursor(self):
        return _Cursor()

    def commit(self):
        pass

    def rollback(self):
        pass


@contextmanager
def get_db():
    _ensure_schema()
    yield _Connection()
