import requests
from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from db import get_db

router = APIRouter()


def _fetch_from_github(token: str):
    repos = []
    page = 1
    while True:
        r = requests.get(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={
                "per_page": 100,
                "page": page,
                "affiliation": "owner",
                "sort": "updated",
            },
            timeout=15,
        )
        if r.status_code != 200:
            print("github repos error:", r.status_code, r.text[:200])
            break
        data = r.json()
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def _upsert(conn, user_id: int, fetched: list) -> int:
    cur = conn.cursor()
    for r in fetched:
        cur.execute(
            """INSERT INTO repos
                 (user_id, github_id, name, full_name, html_url,
                  description, language, stars, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
               ON CONFLICT (user_id, github_id) DO UPDATE SET
                 name = EXCLUDED.name, full_name = EXCLUDED.full_name,
                 html_url = EXCLUDED.html_url, description = EXCLUDED.description,
                 language = EXCLUDED.language, stars = EXCLUDED.stars,
                 fetched_at = NOW()""",
            (
                user_id,
                r["id"],
                r["name"],
                r["full_name"],
                r["html_url"],
                r.get("description"),
                r.get("language"),
                r.get("stargazers_count") or 0,
            ),
        )
    cur.close()
    return len(fetched)


def _save_repos(user_id: int, token: str, conn=None) -> int:
    fetched = _fetch_from_github(token)
    if conn is not None:
        return _upsert(conn, user_id, fetched)
    with get_db() as c:
        return _upsert(c, user_id, fetched)


@router.get("/repos")
def list_repos(user=Depends(get_current_user)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM repos WHERE user_id = %s", (user["id"],))
        count = cur.fetchone()["c"]
        cur.close()

        if count == 0 and user.get("github_token"):
            try:
                _save_repos(user["id"], user["github_token"], conn)
            except Exception as e:
                print("auto-fetch failed:", e)

        cur = conn.cursor()
        cur.execute(
            """SELECT id, github_id, name, full_name, html_url,
                      description, language, stars, fetched_at
               FROM repos WHERE user_id = %s
               ORDER BY stars DESC, name ASC""",
            (user["id"],),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows


@router.post("/repos/refresh")
def refresh_repos(user=Depends(get_current_user)):
    if not user.get("github_token"):
        raise HTTPException(status_code=400, detail="github not connected")
    count = _save_repos(user["id"], user["github_token"])
    return {"count": count}
