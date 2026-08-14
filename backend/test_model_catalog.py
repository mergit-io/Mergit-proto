"""The model picker must only offer models that can actually run.

Every id in `AVAILABLE_MODELS` was set on a live deployment and sent a one-line goal.
Seven of the eight Groq entries answered `model_not_found` or "has been decommissioned",
and two of the five Anthropic entries named models that were retired by the provider in
2025-2026 and now 404. Eleven of thirteen choices in the picker were dead, and the
`is_known_model` validation could not help: it checks the id against this list, and the
list itself was what was wrong.

Two failure modes are covered here:

  1. *Rot* — ids that name models no provider serves. Pruning fixes today; the
     `_FALLBACKS` invariant below keeps the two lists from drifting apart again.
  2. *No credentials* — an id that is perfectly valid but whose provider has no API key
     on this deployment. That is the live instance's actual state: `GROQ_API_KEY` and
     nothing else, so every Anthropic entry fails on selection. The catalogue cannot know
     this statically, so `GET /api/config/models` reports it per request.
"""
import asyncio
import importlib
import json
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


#: Ids proven dead against the provider. Groq entries each returned `model_not_found` or
#: "decommissioned" on the deployment; the Anthropic entries name models the provider
#: retired (Claude 3.5 Sonnet in Oct 2025, Claude 3.5 Haiku in Feb 2026).
RETIRED_OR_UNREACHABLE = {
    "groq/meta-llama/llama-4-maverick-17b-128e-instruct",
    "groq/meta-llama/llama-4-scout-17b-16e-instruct",
    "groq/llama-3.2-90b-vision-preview",
    "groq/llama-3.2-11b-vision-preview",
    "groq/deepseek-r1-distill-llama-70b",
    "groq/qwen-qwq-32b",
    "groq/gemma2-9b-it",
    "anthropic/claude-3-5-sonnet-20241022",
    "anthropic/claude-3-5-haiku-20241022",
}


@pytest.fixture()
def catalog(monkeypatch):
    """`model_config` bound to a temp config dir, so no test touches a real config."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr("config.settings.runtime_config_dir", tmp)
    import model_config as _mc
    importlib.reload(_mc)
    _mc.tmp = tmp
    return _mc


@pytest.fixture()
def env(monkeypatch, catalog):
    """The config router over the same temp dir, with a Groq-only credential set."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    import model_health as _mh
    _mh._cooldowns.clear()

    from api import config as _config
    importlib.reload(_config)
    monkeypatch.setattr(_config, "model_config", catalog)
    monkeypatch.setattr(_config, "model_health", _mh)

    app = FastAPI()
    app.include_router(_config.router)
    client = TestClient(app)
    client.catalog = catalog
    return client


# ── 1. the catalogue must not name models that do not exist ─────────────────────

def test_no_offered_model_is_retired_or_unreachable(catalog):
    offered = {m["id"] for m in catalog.AVAILABLE_MODELS}
    dead = offered & RETIRED_OR_UNREACHABLE
    assert not dead, (
        "the model picker offers ids no provider will serve; selecting one fails every "
        f"subsequent goal with a provider error: {sorted(dead)}"
    )


def test_every_default_is_a_model_the_picker_offers(catalog):
    offered = {m["id"] for m in catalog.AVAILABLE_MODELS}
    for role, model in catalog.DEFAULTS.items():
        assert model in offered, f"default for {role!r} ({model}) is not in the catalogue"


def test_every_offered_model_carries_the_fields_the_picker_renders(catalog):
    for m in catalog.AVAILABLE_MODELS:
        assert {"id", "label", "provider", "tier"} <= set(m), f"incomplete entry: {m}"


# ── 2. the fallback chains must not drift away from the catalogue ───────────────

def test_every_fallback_chain_names_only_offered_models(catalog):
    """The structural guard against this bug returning.

    `llm._FALLBACKS` is a second, independent list of model ids. When the catalogue was
    pruned, nothing forced the chains to be pruned with it — so they kept naming
    decommissioned models, and a fallback that can never succeed is a wasted attempt
    whose error the operator then has to read past.
    """
    import llm
    offered = {m["id"] for m in catalog.AVAILABLE_MODELS}

    unknown = set()
    for primary, chain in llm._FALLBACKS.items():
        if primary not in offered:
            unknown.add(primary)
        unknown.update(set(chain) - offered)

    assert not unknown, (
        "llm._FALLBACKS names models the picker does not offer — the two lists have "
        f"drifted apart again: {sorted(unknown)}"
    )


def test_no_fallback_chain_points_at_itself(catalog):
    import llm
    for primary, chain in llm._FALLBACKS.items():
        assert primary not in chain, f"{primary} lists itself as its own fallback"


# ── 3. a config saved before the prune must not resurrect a dead model ──────────

def test_a_persisted_model_that_is_no_longer_offered_falls_back_to_the_default(catalog):
    """The live deployment persists `model_config.json`. An operator who selected a model
    that this change removes must not keep running it — the id would reach the provider
    and fail every goal, with nothing in the UI showing why."""
    path = os.path.join(catalog.tmp, "model_config.json")
    with open(path, "w") as f:
        json.dump({"coder": "groq/qwen-qwq-32b"}, f)
    catalog._cache = None

    assert catalog.get_model("coder") == catalog.DEFAULTS["coder"], (
        "a decommissioned model persisted in model_config.json was still being used"
    )


def test_a_persisted_model_that_is_still_offered_survives(catalog):
    """The reset above must be surgical — a valid saved choice is the operator's."""
    keep = next(m["id"] for m in catalog.AVAILABLE_MODELS
                if m["id"] != catalog.DEFAULTS["coder"])
    path = os.path.join(catalog.tmp, "model_config.json")
    with open(path, "w") as f:
        json.dump({"coder": keep}, f)
    catalog._cache = None

    assert catalog.get_model("coder") == keep


# ── 4. the API must say which models this deployment can actually use ───────────

def test_each_offered_model_reports_whether_it_is_usable(env):
    body = env.get("/api/config/models").json()
    assert body["available"], "the model picker has nothing to offer"
    for m in body["available"]:
        assert "usable" in m, (
            "the picker cannot tell a working model from one whose provider has no API "
            f"key; every option looks identical: {m}"
        )
        assert isinstance(m["usable"], bool)


def test_a_groq_only_deployment_marks_anthropic_models_unusable(env):
    """The live instance's exact configuration: GROQ_API_KEY and nothing else."""
    by_id = {m["id"]: m for m in env.get("/api/config/models").json()["available"]}

    groq = [m for m in by_id.values() if m["provider"] == "Groq"]
    anthropic = [m for m in by_id.values() if m["provider"] == "Anthropic"]
    assert groq and anthropic, "expected both providers in the catalogue"

    assert all(m["usable"] for m in groq), f"Groq marked unusable with a key set: {groq}"
    assert not any(m["usable"] for m in anthropic), (
        "Anthropic models are offered as selectable with no ANTHROPIC_API_KEY set; "
        "picking one fails every goal"
    )


def test_an_unusable_model_explains_why(env):
    unusable = [m for m in env.get("/api/config/models").json()["available"]
                if not m["usable"]]
    assert unusable, "expected at least one unusable model on a Groq-only deployment"
    for m in unusable:
        assert m.get("unusable_reason"), f"no reason given for {m['id']}"
        assert m["provider"].lower() in m["unusable_reason"].lower()


def test_usability_is_recomputed_per_request_not_frozen_at_import(env, monkeypatch):
    """Keys are set at runtime through `PUT /api/config/keys`. A model that was unusable
    when the process booted must become usable the moment its key exists."""
    before = {m["id"]: m["usable"] for m in env.get("/api/config/models").json()["available"]}
    anthropic = next(m for m in env.get("/api/config/models").json()["available"]
                     if m["provider"] == "Anthropic")
    assert before[anthropic["id"]] is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    after = {m["id"]: m["usable"] for m in env.get("/api/config/models").json()["available"]}
    assert after[anthropic["id"]] is True, (
        "usability was computed once at import; setting a key mid-session left every "
        "model for that provider greyed out until a restart"
    )


def test_the_defaults_are_usable_on_a_groq_only_deployment(env):
    """The deployment invariant: out of the box, with only GROQ_API_KEY, every default
    role must point at a model that can actually run."""
    by_id = {m["id"]: m for m in env.get("/api/config/models").json()["available"]}
    body = env.get("/api/config/models").json()
    for role, model in body["defaults"].items():
        assert by_id[model]["usable"], (
            f"the default model for {role!r} cannot run on this deployment ({model})"
        )


def test_the_existing_contract_is_unchanged(env):
    """The picker still reads `models`, `available` and `defaults` — annotation is
    additive, so a frontend that ignores `usable` keeps working."""
    body = env.get("/api/config/models").json()
    assert set(body["models"]) == set(body["defaults"])
    assert all({"id", "label", "provider", "tier"} <= set(m) for m in body["available"])


def test_selecting_a_usable_model_still_saves(env):
    target = next(m["id"] for m in env.get("/api/config/models").json()["available"]
                  if m["usable"])
    assert env.put("/api/config/models", json={"models": {"coder": target}}).status_code == 200
    assert env.get("/api/config/models").json()["models"]["coder"] == target


def test_a_model_without_credentials_can_still_be_selected(env):
    """Deliberate: an operator may set the model first and paste the key second. The
    picker warns, it does not block — blocking would make that order impossible."""
    target = next(m["id"] for m in env.get("/api/config/models").json()["available"]
                  if not m["usable"])
    assert env.put("/api/config/models", json={"models": {"coder": target}}).status_code == 200
