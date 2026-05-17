import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import auth
import projects
import repos
import init_db

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

app = FastAPI()


@app.on_event("startup")
def on_startup():
    try:
        init_db.main()
    except Exception as e:
        print(f"[startup] DB init skipped: {e}")

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
