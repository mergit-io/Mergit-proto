"""Contract tests for /api/goals and /api/tasks.

Neither router had a test file. Two defects found against the live deployment are
pinned here:

  - `limit` was passed straight through to `LIMIT ?`, and SQLite reads a negative limit
    as unbounded. `/api/goals?limit=-1` and `/api/economy/proofs?limit=-1` returned the
    entire table from an unauthenticated endpoint.
  - `POST /api/goals` accepted a 20,000-character body and stored it whole, so anyone
    with the URL could write unbounded rows into the SQLite file.
"""
import asyncio
import importlib
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import settings


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.db_path", os.path.join(tmp, "goals.db"))

    import db as _db
    importlib.reload(_db)
    from api import goals as _goals
    from api import tasks as _tasks
    importlib.reload(_goals)
    importlib.reload(_tasks)
    monkeypatch.setattr(_goals, "db", _db)
    monkeypatch.setattr(_tasks, "db", _db)

    app = FastAPI()
    app.include_router(_goals.router)
    app.include_router(_tasks.router)

    asyncio.run(_db.init_db())
    c = TestClient(app)
    c.db = _db
    return c


# ── submission ──────────────────────────────────────────────────────────────────

def test_submitting_a_goal_returns_202_and_a_new_goal(client):
    r = client.post("/api/goals", json={"goal": "  Summarise the README  "})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "NEW"
    assert body["goal_id"]
    assert isinstance(body["created_at"], int)

    stored = asyncio.run(client.db.get_goal(body["goal_id"]))
    assert stored.goal_text == "Summarise the README", "the goal was not trimmed"


@pytest.mark.parametrize("goal", ["", "   ", "\n\t "])
def test_an_empty_goal_is_rejected(client, goal):
    r = client.post("/api/goals", json={"goal": goal})
    assert r.status_code == 400
    assert r.json()["detail"] == "goal must not be empty"


def test_a_missing_goal_field_is_a_422(client):
    assert client.post("/api/goals", json={}).status_code == 422


def test_a_non_string_goal_is_a_422(client):
    assert client.post("/api/goals", json={"goal": 123}).status_code == 422


# ── size cap ────────────────────────────────────────────────────────────────────

def test_an_oversized_goal_is_rejected(client):
    oversized = "x" * (settings.max_goal_chars + 1)
    r = client.post("/api/goals", json={"goal": oversized})

    assert r.status_code == 413, (
        f"a {len(oversized)}-character goal was accepted from an unauthenticated "
        "endpoint and stored whole"
    )
    assert str(settings.max_goal_chars) in r.json()["detail"]
    assert asyncio.run(client.db.list_goals()) == [], "the oversized goal was persisted anyway"


def test_a_goal_at_the_limit_is_accepted(client):
    """The cap must not block a long but legitimate problem statement."""
    r = client.post("/api/goals", json={"goal": "y" * settings.max_goal_chars})
    assert r.status_code == 202


# ── listing and pagination ──────────────────────────────────────────────────────

def _seed(client, n):
    return [client.post("/api/goals", json={"goal": f"goal {i}"}).json()["goal_id"] for i in range(n)]


def test_listing_returns_goals_newest_first(client):
    _seed(client, 3)
    body = client.get("/api/goals").json()
    assert len(body["goals"]) == 3
    assert body["total"] == 3
    created = [g["created_at"] for g in body["goals"]]
    assert created == sorted(created, reverse=True)


def test_limit_and_offset_page_through_results(client):
    _seed(client, 5)
    first = client.get("/api/goals?limit=2").json()["goals"]
    second = client.get("/api/goals?limit=2&offset=2").json()["goals"]
    assert len(first) == 2 and len(second) == 2
    assert {g["goal_id"] for g in first}.isdisjoint({g["goal_id"] for g in second})


def test_status_filter_narrows_the_list(client):
    _seed(client, 2)
    assert len(client.get("/api/goals?status=NEW").json()["goals"]) == 2
    assert client.get("/api/goals?status=COMPLETED").json()["goals"] == []


@pytest.mark.parametrize("query", ["limit=-1", "limit=0", "offset=-1", "limit=99999"])
def test_out_of_range_pagination_is_rejected(client, query):
    """`LIMIT -1` is unbounded in SQLite — the whole table, unauthenticated."""
    _seed(client, 3)
    r = client.get(f"/api/goals?{query}")
    assert r.status_code == 422, (
        f"?{query} returned {r.status_code}; an unvalidated limit reaches SQLite directly"
    )


def test_a_non_integer_limit_is_a_422(client):
    assert client.get("/api/goals?limit=abc").status_code == 422


# ── retrieval ───────────────────────────────────────────────────────────────────

def test_getting_a_goal_returns_its_full_record(client):
    goal_id = client.post("/api/goals", json={"goal": "read me back"}).json()["goal_id"]
    body = client.get(f"/api/goals/{goal_id}").json()

    assert body["goal_id"] == goal_id
    assert body["goal_text"] == "read me back"
    assert body["status"] == "NEW"
    assert body["plan"] is None
    assert body["tasks"] == []
    assert body["trace_id"]


def test_unknown_goal_is_a_404(client):
    r = client.get("/api/goals/nope-00000000")
    assert r.status_code == 404
    assert r.json()["detail"] == "Goal not found"


def test_tasks_of_an_unknown_goal_is_a_404(client):
    assert client.get("/api/goals/nope-00000000/tasks").status_code == 404


def test_unknown_task_is_a_404(client):
    r = client.get("/api/tasks/nope-00000000")
    assert r.status_code == 404
    assert r.json()["detail"] == "Task not found"


def test_tasks_are_listed_and_individually_retrievable(client):
    goal_id = client.post("/api/goals", json={"goal": "with tasks"}).json()["goal_id"]
    goal = asyncio.run(client.db.get_goal(goal_id))
    asyncio.run(client.db.create_tasks(
        [
            {"id": "t1", "agent": "researcher", "description": "look it up",
             "inputs": {"q": "x"}, "depends_on": []},
            {"id": "t2", "agent": "writer", "description": "write it up",
             "inputs": {"src": "{{t1.output}}"}, "depends_on": ["t1"]},
        ],
        goal_id, goal.trace_id,
    ))

    listed = client.get(f"/api/goals/{goal_id}/tasks").json()["tasks"]
    assert {t["agent_name"] for t in listed} == {"researcher", "writer"}
    assert {t["goal_id"] for t in listed} == {goal_id}

    one = client.get("/api/tasks/t2").json()
    assert one["agent_name"] == "writer"
    assert one["inputs"] == {"src": "{{t1.output}}"}
    assert one["attempt_count"] == 0
    assert one["output"] is None
