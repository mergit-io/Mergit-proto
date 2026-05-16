"""
GitHub Actions & branch protection management API.
Lets the frontend inspect and trigger changes to workflows and rulesets.
"""
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import db
from tools.github_ops import (
    github_list_workflows,
    github_get_branch_protection,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("/workflows")
async def list_workflows(repo: str = Query(..., description="owner/repo")):
    result = await github_list_workflows({"repo": repo})
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to list workflows"))
    return result


@router.get("/protection")
async def get_protection(repo: str = Query(..., description="owner/repo"), branch: str = Query(None)):
    args = {"repo": repo}
    if branch:
        args["branch"] = branch
    result = await github_get_branch_protection(args)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to get branch protection"))
    return result


class ActionGoalBody(BaseModel):
    repo: str
    instruction: str


@router.post("/goal")
async def create_action_goal(body: ActionGoalBody):
    """Create a goal from a natural language instruction about GitHub Actions or branch rules."""
    goal_text = (
        f"GitHub Actions / repository automation task for {body.repo}.\n\n"
        f"Instruction: {body.instruction}\n\n"
        f"Repository: {body.repo}\n\n"
        "Steps:\n"
        "1. Read the current repository structure and existing workflows (.github/workflows/)\n"
        "2. Read existing branch protection rules if relevant\n"
        "3. Make the requested change — create/update a workflow YAML or update branch protection rules\n"
        "4. For workflow changes: create a PR with the new/updated YAML file\n"
        "5. For branch protection changes: apply them directly via github_set_branch_protection\n"
        "6. Report what was done"
    )
    goal = await db.create_goal(goal_text)
    return {"ok": True, "goal_id": goal.id, "repo": body.repo}
