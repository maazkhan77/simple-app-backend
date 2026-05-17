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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
