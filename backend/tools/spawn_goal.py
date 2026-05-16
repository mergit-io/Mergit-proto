"""
Allows any agent to autonomously spawn a new goal mid-execution.
Used when an agent discovers work that requires a full multi-agent pipeline
beyond its own capability — e.g. a researcher finds a bug and spawns a fix goal.
"""
import logging

from tracing import trace

logger = logging.getLogger(__name__)


@trace("spawn_goal")
async def spawn_goal(args: dict) -> dict:
    import db
    goal_text = args["goal"]
    reason = args.get("reason", "")
    parent_goal_id = args.get("_goal_id", "")  # injected by agent_runner

    goal = await db.create_goal(goal_text)
    logger.info(
        "spawn_goal: new goal %s spawned by parent %s — %s",
        goal.id, parent_goal_id, reason or goal_text[:60],
    )
    return {
        "ok": True,
        "goal_id": goal.id,
        "status": "NEW",
        "message": f"New goal created and queued for autonomous execution: {goal.id}",
    }


SCHEMA = {
    "description": (
        "Spawn a new autonomous goal. Use this when you discover work that requires "
        "a full multi-agent pipeline beyond your current task — e.g. you found a bug "
        "that needs researching, fixing, and a PR. The new goal runs fully autonomously "
        "without human intervention."
    ),
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": "Full natural language description of the new goal to execute",
        },
        "reason": {
            "type": "string",
            "description": "Why you are spawning this goal — used for logging",
        },
    },
    "required": ["goal"],
}
