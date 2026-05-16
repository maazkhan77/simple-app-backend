from dotenv import load_dotenv

load_dotenv()

from db import get_db


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


def main():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(SCHEMA)
        cur.close()
    print("tables created")


if __name__ == "__main__":
    main()
