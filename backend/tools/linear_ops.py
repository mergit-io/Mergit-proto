"""Linear issue-tracker operations for agents.

Linear is the system of record for *whether the work is done*, which is a different
question from whether a pull request exists. An agent that opens a PR and stops has done
half a job; the half that a team actually reads is the ticket moving to In Review with
the PR attached.

Three things are handled here rather than left to the model, because a model gets each of
them wrong in a way that looks like success:

* **Names in, ids out.** Linear's API speaks UUIDs. Humans and models write `ENG`,
  `ENG-42` and `In Review`. Teams, states and issue identifiers are all resolved here.
* **GraphQL errors arrive with HTTP 200.** A malformed mutation returns
  `{"errors": [...]}` and status 200, and `success: false` inside `issueCreate` is
  another way to fail while looking fine. Both are turned into `ok: false`.
* **A created issue returns its `url`.** `agent_runner._claimed_without_artifact` rejects
  an action that claims to have made something addressable with no address, and that
  guard is only useful if the tool actually hands back the address.
"""
import logging
import re

import httpx

from tools.placeholders import refuse_if_unfilled as _refuse_if_unfilled
from tools.service_client import audit as _audit
from tools.service_client import credential_check as _credential_check
from tools.service_client import token as _token

logger = logging.getLogger(__name__)

_API = "https://api.linear.app/graphql"
_PROVIDER = "linear"
_TIMEOUT = 25

#: `ENG-42` — a Linear issue identifier as it is written everywhere except the API.
_IDENTIFIER = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)-(\d+)$")
#: A UUID, which is what the API actually wants.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

#: team key (upper) → team id, per process. Teams do not change id.
_TEAM_IDS: dict[str, str] = {}


def _auth_header(tok: str) -> str:
    """Linear takes a personal API key raw and an OAuth token as a Bearer.

    Sending `Bearer lin_api_…` fails authentication, and sending an OAuth token raw fails
    the same way, so this is not a stylistic choice — the prefix decides the format.
    """
    return tok if tok.startswith("lin_api_") else f"Bearer {tok}"


async def _gql(args: dict, query: str, variables: dict | None = None) -> dict:
    """One GraphQL call. Returns `{"ok": True, "data": ...}` or `{"ok": False, "error": ...}`."""
    tok = await _token(_PROVIDER, args)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _API,
                headers={"Authorization": _auth_header(tok), "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
    except Exception as e:
        return {"ok": False, "error": f"Linear request failed: {e}"}

    if resp.status_code in (401, 403):
        return {"ok": False, "error": "Linear rejected the API key (401/403) — reconnect Linear"}
    try:
        body = resp.json()
    except Exception:
        return {"ok": False, "error": f"Linear returned non-JSON (HTTP {resp.status_code})"}

    # HTTP 200 with an `errors` array is Linear's normal way to report a bad query. Reading
    # only the status code is how a mutation that never ran gets reported as done.
    if body.get("errors"):
        msg = "; ".join(str(e.get("message", e)) for e in body["errors"])[:600]
        return {"ok": False, "error": f"Linear GraphQL error: {msg}"}
    if body.get("data") is None:
        return {"ok": False, "error": "Linear returned no data"}
    return {"ok": True, "data": body["data"]}


async def _resolve_team(args: dict, team: str) -> tuple[str, str | None]:
    """(team_id, error). Accepts a UUID, a team key (`ENG`), or a team name."""
    team = (team or "").strip()
    if not team:
        return "", ("team is required — pass the team key (for example ENG). "
                    "linear_list_teams shows what exists.")
    if _UUID.match(team):
        return team, None
    if team.upper() in _TEAM_IDS:
        return _TEAM_IDS[team.upper()], None

    res = await _gql(args, "query { teams(first: 100) { nodes { id key name } } }")
    if not res["ok"]:
        return "", res["error"]
    nodes = res["data"]["teams"]["nodes"]
    for t in nodes:
        _TEAM_IDS[t["key"].upper()] = t["id"]
    for t in nodes:
        if team.upper() in (t["key"].upper(), t["name"].upper()):
            return t["id"], None
    known = ", ".join(t["key"] for t in nodes) or "none"
    return "", f"no Linear team matches {team!r}. Teams available: {known}"


async def _resolve_state(args: dict, team_id: str, state: str) -> tuple[str, str | None]:
    """(state_id, error). Accepts a UUID or a workflow-state name such as `In Review`."""
    state = (state or "").strip()
    if not state:
        return "", "state is required"
    if _UUID.match(state):
        return state, None
    res = await _gql(
        args,
        """query($teamId: String!) {
             team(id: $teamId) { states(first: 50) { nodes { id name type } } }
           }""",
        {"teamId": team_id},
    )
    if not res["ok"]:
        return "", res["error"]
    nodes = (res["data"].get("team") or {}).get("states", {}).get("nodes", [])
    for s in nodes:
        if s["name"].lower() == state.lower():
            return s["id"], None
    known = ", ".join(s["name"] for s in nodes) or "none"
    return "", f"no workflow state named {state!r} on this team. States: {known}"


async def _resolve_issue(args: dict, issue: str) -> tuple[str, str | None]:
    """(issue_id, error). Accepts a UUID or an identifier such as `ENG-42`."""
    issue = (issue or "").strip()
    if not issue:
        return "", "issue is required"
    if _UUID.match(issue):
        return issue, None
    m = _IDENTIFIER.match(issue)
    if not m:
        return "", f"{issue!r} is neither a Linear issue id nor an identifier like ENG-42"
    key, number = m.group(1).upper(), int(m.group(2))
    res = await _gql(
        args,
        """query($key: String!, $number: Float!) {
             issues(filter: { team: { key: { eq: $key } }, number: { eq: $number } }, first: 1) {
               nodes { id identifier }
             }
           }""",
        {"key": key, "number": number},
    )
    if not res["ok"]:
        return "", res["error"]
    nodes = res["data"]["issues"]["nodes"]
    if not nodes:
        return "", f"no Linear issue {issue}"
    return nodes[0]["id"], None


# ── Teams ────────────────────────────────────────────────────────────────────────

async def linear_list_teams(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    res = await _gql(args, "query { teams(first: 100) { nodes { id key name } } }")
    if not res["ok"]:
        return res
    nodes = res["data"]["teams"]["nodes"]
    for t in nodes:
        _TEAM_IDS[t["key"].upper()] = t["id"]
    await _audit(_PROVIDER, args, "linear_list_teams")
    return {"ok": True, "teams": [{"key": t["key"], "name": t["name"], "id": t["id"]}
                                  for t in nodes]}


LINEAR_LIST_TEAMS_SCHEMA = {
    "description": "List Linear teams with their keys and ids. Call this first if you do not know the team key.",
    "type": "object",
    "properties": {},
    "required": [],
}


async def linear_list_states(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    team_id, err = await _resolve_team(args, args.get("team", ""))
    if err:
        return {"ok": False, "error": err}
    res = await _gql(
        args,
        """query($teamId: String!) {
             team(id: $teamId) { states(first: 50) { nodes { id name type } } }
           }""",
        {"teamId": team_id},
    )
    if not res["ok"]:
        return res
    nodes = (res["data"].get("team") or {}).get("states", {}).get("nodes", [])
    await _audit(_PROVIDER, args, "linear_list_states", target=team_id)
    return {"ok": True, "states": [{"name": s["name"], "type": s["type"], "id": s["id"]}
                                   for s in nodes]}


LINEAR_LIST_STATES_SCHEMA = {
    "description": "List the workflow states of a Linear team (Todo, In Progress, In Review, Done...).",
    "type": "object",
    "properties": {"team": {"type": "string", "description": "Team key (ENG), name, or id"}},
    "required": ["team"],
}


# ── Create ───────────────────────────────────────────────────────────────────────

async def linear_create_issue(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    title = (args.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title is required"}
    # Run 0e9fefe4 planned `"issue_description": "Bug fix PR: {{0e9fefe4_t3.output.url}}"` —
    # a task referring to its own not-yet-existent output. That template can never resolve,
    # and a ticket carrying it says nothing to the person who opens it.
    blanks = _refuse_if_unfilled(f"{title}\n{args.get('description') or ''}", "this Linear issue")
    if blanks:
        return blanks
    team_id, err = await _resolve_team(args, args.get("team", ""))
    if err:
        return {"ok": False, "error": err}

    variables: dict = {
        "teamId": team_id,
        "title": title[:255],
        "description": (args.get("description") or "")[:60000],
    }
    state_arg = (args.get("state") or "").strip()
    if state_arg:
        state_id, err = await _resolve_state(args, team_id, state_arg)
        if err:
            return {"ok": False, "error": err}
        variables["stateId"] = state_id

    mutation = """
      mutation($teamId: String!, $title: String!, $description: String, $stateId: String) {
        issueCreate(input: {
          teamId: $teamId, title: $title, description: $description, stateId: $stateId
        }) {
          success
          issue { id identifier title url state { name } }
        }
      }"""
    res = await _gql(args, mutation, variables)
    if not res["ok"]:
        await _audit(_PROVIDER, args, "linear_create_issue", target=team_id, outcome="error")
        return res
    payload = res["data"]["issueCreate"]
    # `success: false` with no `errors` array is Linear's quiet refusal — a permission it
    # will not name. Reported as a failure rather than returned as an issue-shaped None.
    if not payload.get("success") or not payload.get("issue"):
        await _audit(_PROVIDER, args, "linear_create_issue", target=team_id, outcome="error")
        return {"ok": False, "error": "Linear refused to create the issue (success=false)"}
    issue = payload["issue"]
    await _audit(_PROVIDER, args, "linear_create_issue", target=issue["identifier"])
    return {"ok": True, "id": issue["id"], "identifier": issue["identifier"],
            "title": issue["title"], "url": issue["url"],
            "state": (issue.get("state") or {}).get("name", "")}


LINEAR_CREATE_ISSUE_SCHEMA = {
    "description": (
        "Create a Linear issue and return its identifier (ENG-42) and URL. Use this to put "
        "work on the board — link the GitHub PR in the description so the ticket and the "
        "code point at each other."
    ),
    "type": "object",
    "properties": {
        "team": {"type": "string", "description": "Team key (ENG), name, or id"},
        "title": {"type": "string", "description": "Issue title — imperative, under 70 chars"},
        "description": {"type": "string", "description": "Markdown body. Include real URLs, not placeholders."},
        "state": {"type": "string", "description": "Optional starting state, e.g. 'Todo' or 'In Review'"},
    },
    "required": ["team", "title"],
}


# ── Read back ────────────────────────────────────────────────────────────────────

async def linear_get_issue(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    issue_id, err = await _resolve_issue(args, args.get("issue", ""))
    if err:
        return {"ok": False, "error": err}
    res = await _gql(
        args,
        """query($id: String!) {
             issue(id: $id) {
               id identifier title description url
               state { name type }
               team { key }
               comments(first: 20) { nodes { id body createdAt } }
             }
           }""",
        {"id": issue_id},
    )
    if not res["ok"]:
        return res
    issue = res["data"].get("issue")
    if not issue:
        return {"ok": False, "error": "no such Linear issue"}
    await _audit(_PROVIDER, args, "linear_get_issue", target=issue["identifier"])
    return {
        "ok": True, "id": issue["id"], "identifier": issue["identifier"],
        "title": issue["title"], "description": (issue.get("description") or "")[:8000],
        "url": issue["url"], "state": (issue.get("state") or {}).get("name", ""),
        "team": (issue.get("team") or {}).get("key", ""),
        "comments": [{"body": c["body"][:2000], "created_at": c["createdAt"]}
                     for c in (issue.get("comments") or {}).get("nodes", [])],
    }


LINEAR_GET_ISSUE_SCHEMA = {
    "description": (
        "Read a Linear issue by identifier (ENG-42) or id — title, description, current "
        "state and comments. Use this to confirm a change actually landed."
    ),
    "type": "object",
    "properties": {"issue": {"type": "string", "description": "Identifier like ENG-42, or the issue id"}},
    "required": ["issue"],
}


# ── Update ───────────────────────────────────────────────────────────────────────

async def linear_update_issue(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    issue_id, err = await _resolve_issue(args, args.get("issue", ""))
    if err:
        return {"ok": False, "error": err}

    # The team is needed to resolve a state name, and the issue knows its own team — so it
    # is read rather than asked for. A model that had to supply it would guess.
    current = await _gql(
        args,
        "query($id: String!) { issue(id: $id) { id identifier team { id } } }",
        {"id": issue_id},
    )
    if not current["ok"]:
        return current
    issue_row = current["data"].get("issue")
    if not issue_row:
        return {"ok": False, "error": "no such Linear issue"}

    blanks = _refuse_if_unfilled(
        f"{args.get('title') or ''}\n{args.get('description') or ''}", "this Linear update")
    if blanks:
        return blanks

    variables: dict = {"id": issue_id}
    if args.get("title"):
        variables["title"] = args["title"][:255]
    if args.get("description"):
        variables["description"] = args["description"][:60000]
    if args.get("state"):
        state_id, err = await _resolve_state(args, issue_row["team"]["id"], args["state"])
        if err:
            return {"ok": False, "error": err}
        variables["stateId"] = state_id
    if len(variables) == 1:
        return {"ok": False, "error": "nothing to update — pass state, title or description"}

    mutation = """
      mutation($id: String!, $title: String, $description: String, $stateId: String) {
        issueUpdate(id: $id, input: { title: $title, description: $description, stateId: $stateId }) {
          success
          issue { id identifier title url state { name } }
        }
      }"""
    res = await _gql(args, mutation, variables)
    if not res["ok"]:
        await _audit(_PROVIDER, args, "linear_update_issue",
                     target=issue_row["identifier"], outcome="error")
        return res
    payload = res["data"]["issueUpdate"]
    if not payload.get("success") or not payload.get("issue"):
        await _audit(_PROVIDER, args, "linear_update_issue",
                     target=issue_row["identifier"], outcome="error")
        return {"ok": False, "error": "Linear refused the update (success=false)"}
    issue = payload["issue"]
    await _audit(_PROVIDER, args, "linear_update_issue", target=issue["identifier"])
    return {"ok": True, "id": issue["id"], "identifier": issue["identifier"],
            "url": issue["url"], "state": (issue.get("state") or {}).get("name", "")}


LINEAR_UPDATE_ISSUE_SCHEMA = {
    "description": (
        "Update a Linear issue — move it to another workflow state, or change its title or "
        "description. Moving a ticket to 'In Review' when the PR opens is what makes the "
        "board true."
    ),
    "type": "object",
    "properties": {
        "issue": {"type": "string", "description": "Identifier like ENG-42, or the issue id"},
        "state": {"type": "string", "description": "Target state name, e.g. 'In Review' or 'Done'"},
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["issue"],
}


# ── Comment ──────────────────────────────────────────────────────────────────────

async def linear_comment(args: dict) -> dict:
    missing = await _credential_check(_PROVIDER, args)
    if missing:
        return missing
    body = (args.get("body") or "").strip()
    if not body:
        return {"ok": False, "error": "body is required"}
    blanks = _refuse_if_unfilled(body, "this Linear comment")
    if blanks:
        return blanks
    issue_id, err = await _resolve_issue(args, args.get("issue", ""))
    if err:
        return {"ok": False, "error": err}

    res = await _gql(
        args,
        """mutation($issueId: String!, $body: String!) {
             commentCreate(input: { issueId: $issueId, body: $body }) {
               success
               comment { id url createdAt }
             }
           }""",
        {"issueId": issue_id, "body": body[:60000]},
    )
    if not res["ok"]:
        await _audit(_PROVIDER, args, "linear_comment", target=issue_id, outcome="error")
        return res
    payload = res["data"]["commentCreate"]
    if not payload.get("success") or not payload.get("comment"):
        await _audit(_PROVIDER, args, "linear_comment", target=issue_id, outcome="error")
        return {"ok": False, "error": "Linear refused to post the comment (success=false)"}
    comment = payload["comment"]
    await _audit(_PROVIDER, args, "linear_comment", target=issue_id)
    return {"ok": True, "id": comment["id"], "url": comment.get("url", ""),
            "created_at": comment.get("createdAt", "")}


LINEAR_COMMENT_SCHEMA = {
    "description": "Post a comment on a Linear issue. Use real URLs for anything you claim to have done.",
    "type": "object",
    "properties": {
        "issue": {"type": "string", "description": "Identifier like ENG-42, or the issue id"},
        "body": {"type": "string", "description": "Markdown comment body"},
    },
    "required": ["issue", "body"],
}
