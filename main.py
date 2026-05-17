import os

from dotenv import load_dotenv

load_dotenv()

print(f"[boot] DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
print(f"[boot] SECRET_KEY set: {bool(os.getenv('SECRET_KEY'))}")
print(f"[boot] GITHUB_CLIENT_ID set: {bool(os.getenv('GITHUB_CLIENT_ID'))}")
print(f"[boot] FRONTEND_URL: {os.getenv('FRONTEND_URL')}")
print(f"[boot] BACKEND_URL: {os.getenv('BACKEND_URL')}")
print(f"[boot] PORT: {os.getenv('PORT')}")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import projects
import repos

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(projects.router)


@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/debug/env")
def debug_env():
    return {
        "DATABASE_URL": bool(os.getenv("DATABASE_URL")),
        "SECRET_KEY": bool(os.getenv("SECRET_KEY")),
        "GITHUB_CLIENT_ID": bool(os.getenv("GITHUB_CLIENT_ID")),
        "GITHUB_CLIENT_SECRET": bool(os.getenv("GITHUB_CLIENT_SECRET")),
        "GOOGLE_CLIENT_ID": bool(os.getenv("GOOGLE_CLIENT_ID")),
        "GOOGLE_CLIENT_SECRET": bool(os.getenv("GOOGLE_CLIENT_SECRET")),
        "FRONTEND_URL": os.getenv("FRONTEND_URL"),
        "BACKEND_URL": os.getenv("BACKEND_URL"),
        "PORT": os.getenv("PORT"),
    }


@app.get("/debug/db")
def debug_db():
    try:
        from db import get_db
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            cur.close()
        return {"db": "connected", "result": dict(row)}
    except Exception as e:
        return {"db": "failed", "error": str(e)}


@app.get("/debug/net")
def debug_net():
    import socket
    from urllib.parse import urlparse
    results = {}
    db_url = os.getenv("DATABASE_URL", "")
    neon_host = urlparse(db_url).hostname if db_url else None

    hosts = [
        ("www.google.com", 443, "google_443"),
        ("api.github.com", 443, "github_443"),
        ("github.com", 443, "github_root_443"),
    ]
    if neon_host:
        hosts.append((neon_host, 443, "neon_443"))

    for host, port, label in hosts:
        # DNS lookup first with timeout via socket.getaddrinfo (no direct timeout, but fast)
        try:
            socket.setdefaulttimeout(3)
            ip = socket.gethostbyname(host)
            results[f"{label}_dns"] = ip
        except Exception as e:
            results[f"{label}_dns"] = f"FAIL: {e}"
            continue

        # TCP connect test with 3s timeout
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        try:
            s.connect((host, port))
            results[label] = "TCP OK"
        except Exception as e:
            results[label] = f"TCP FAIL: {e}"
        finally:
            s.close()
    socket.setdefaulttimeout(None)
    return {"build": "1750f23+tcp", "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
