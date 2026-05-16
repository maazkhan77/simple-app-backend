from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from db import get_db

router = APIRouter()


class CreateProjectBody(BaseModel):
    repo_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    branch: Optional[str] = None


@router.get("/projects")
def list_projects(user=Depends(get_current_user)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id, p.name, p.description, p.branch, p.status,
                      p.created_at, p.repo_id,
                      r.full_name AS repo_full_name,
                      r.html_url  AS repo_url
               FROM projects p
               LEFT JOIN repos r ON r.id = p.repo_id
               WHERE p.user_id = %s
               ORDER BY p.created_at DESC""",
            (user["id"],),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    return rows


@router.post("/projects")
def create_project(body: CreateProjectBody, user=Depends(get_current_user)):
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name, description FROM repos WHERE id = %s AND user_id = %s",
            (body.repo_id, user["id"]),
        )
        repo = cur.fetchone()
        if not repo:
            cur.close()
            raise HTTPException(status_code=404, detail="repo not found")

        name = body.name or repo["name"]
        description = body.description if body.description is not None else repo["description"]
        branch = body.branch or "main"

        cur.execute(
            """INSERT INTO projects (user_id, repo_id, name, description, branch)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, name, description, branch, status, created_at, repo_id""",
            (user["id"], body.repo_id, name, description, branch),
        )
        proj = dict(cur.fetchone())
        cur.close()
    return proj


@router.post("/projects/{project_id}/deploy")
def deploy_project(project_id: int, user=Depends(get_current_user)):
    # TODO: actually deploy to k8s
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE projects
               SET status = 'deployed'
               WHERE id = %s AND user_id = %s
               RETURNING id, status""",
            (project_id, user["id"]),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            raise HTTPException(status_code=404, detail="project not found")
        cur.close()
    return dict(row)
