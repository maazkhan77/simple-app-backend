import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import requests
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

from db import get_db

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
COOKIE_SECURE = BACKEND_URL.startswith("https")

COOKIE_NAME = "session"
JWT_ALGO = "HS256"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7

router = APIRouter()


def make_jwt(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=COOKIE_MAX_AGE),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGO)


def set_session_cookie(resp: Response, token: str):
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="none" if COOKIE_SECURE else "lax",
        secure=COOKIE_SECURE,
        max_age=COOKIE_MAX_AGE,
        path="/",
    )


def _user_from_token(token: str | None):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGO])
        user_id = int(payload["sub"])
    except jwt.PyJWTError:
        return None

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        cur.close()
    return dict(user) if user else None


def get_current_user(session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    user = _user_from_token(session)
    if not user:
        raise HTTPException(status_code=401, detail="not logged in")
    return user


def get_current_user_optional(session: str | None = Cookie(default=None, alias=COOKIE_NAME)):
    return _user_from_token(session)


@router.get("/auth/github")
def github_login():
    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/github/callback",
        "scope": "read:user user:email repo",
    }
    return RedirectResponse(
        f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    )


@router.get("/auth/github/callback")
def github_callback(code: str | None = None, error: str | None = None, user=Depends(get_current_user_optional)):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}/?error=access_denied")

    token_resp = requests.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        },
        headers={"Accept": "application/json"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/?error=github_failed")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}/?error=no_github_token")

    gh_resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if gh_resp.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/?error=github_user")
    gh = gh_resp.json()

    email = gh.get("email")
    if not email:
        em = requests.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if em.status_code == 200:
            for e in em.json():
                if e.get("primary"):
                    email = e.get("email")
                    break

    github_id = str(gh["id"])
    name = gh.get("name") or gh.get("login")
    avatar = gh.get("avatar_url")

    with get_db() as conn:
        cur = conn.cursor()

        if user:
            cur.execute(
                """UPDATE users
                   SET github_id = %s, github_token = %s,
                       avatar_url = COALESCE(avatar_url, %s)
                   WHERE id = %s""",
                (github_id, access_token, avatar, user["id"]),
            )
            user_id = user["id"]
        else:
            cur.execute("SELECT id FROM users WHERE github_id = %s", (github_id,))
            row = cur.fetchone()
            if row:
                user_id = row["id"]
                cur.execute(
                    "UPDATE users SET github_token = %s WHERE id = %s",
                    (access_token, user_id),
                )
            elif email:
                cur.execute("SELECT id FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                if row:
                    user_id = row["id"]
                    cur.execute(
                        "UPDATE users SET github_id = %s, github_token = %s WHERE id = %s",
                        (github_id, access_token, user_id),
                    )
                else:
                    cur.execute(
                        """INSERT INTO users (email, name, avatar_url, github_id, github_token)
                           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
                        (email, name, avatar, github_id, access_token),
                    )
                    user_id = cur.fetchone()["id"]
            else:
                cur.execute(
                    """INSERT INTO users (name, avatar_url, github_id, github_token)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (name, avatar, github_id, access_token),
                )
                user_id = cur.fetchone()["id"]

        cur.close()

    resp = RedirectResponse(f"{FRONTEND_URL}/dashboard")
    set_session_cookie(resp, make_jwt(user_id))
    return resp


@router.get("/auth/google")
def google_login():
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{BACKEND_URL}/auth/google/callback",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(
        f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    )


@router.get("/auth/google/callback")
def google_callback(code: str | None = None, error: str | None = None):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}/?error=access_denied")

    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": f"{BACKEND_URL}/auth/google/callback",
        },
        timeout=10,
    )
    if token_resp.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/?error=google_failed")

    access_token = token_resp.json().get("access_token")
    if not access_token:
        return RedirectResponse(f"{FRONTEND_URL}/?error=no_google_token")

    info = requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if info.status_code != 200:
        return RedirectResponse(f"{FRONTEND_URL}/?error=google_user")
    g = info.json()

    google_id = str(g["id"])
    email = g.get("email")
    name = g.get("name")
    avatar = g.get("picture")

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("SELECT id FROM users WHERE google_id = %s", (google_id,))
        row = cur.fetchone()
        if row:
            user_id = row["id"]
        elif email:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row:
                user_id = row["id"]
                cur.execute(
                    "UPDATE users SET google_id = %s WHERE id = %s", (google_id, user_id)
                )
            else:
                cur.execute(
                    """INSERT INTO users (email, name, avatar_url, google_id)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (email, name, avatar, google_id),
                )
                user_id = cur.fetchone()["id"]
        else:
            cur.execute(
                """INSERT INTO users (name, avatar_url, google_id)
                   VALUES (%s, %s, %s) RETURNING id""",
                (name, avatar, google_id),
            )
            user_id = cur.fetchone()["id"]

        cur.close()

    resp = RedirectResponse(f"{FRONTEND_URL}/dashboard")
    set_session_cookie(resp, make_jwt(user_id))
    return resp


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "avatar_url": user["avatar_url"],
        "has_github": bool(user.get("github_id")),
        "has_google": bool(user.get("google_id")),
    }
