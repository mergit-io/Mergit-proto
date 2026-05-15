"""
In-memory model health tracker.
When a model hits a hard rate limit (daily quota, resource_exhausted),
it's marked unhealthy for a cooldown period. Subsequent acompletion() calls
skip unhealthy models and go directly to their fallbacks.
"""
import time

_cooldowns: dict[str, float] = {}  # model_id → unhealthy_until (unix timestamp)


def mark_unhealthy(model: str, cooldown_secs: float) -> None:
    until = time.time() + max(cooldown_secs, 60)
    if _cooldowns.get(model, 0) < until:
        _cooldowns[model] = until


def is_healthy(model: str) -> bool:
    until = _cooldowns.get(model, 0)
    if until <= time.time():
        _cooldowns.pop(model, None)
        return True
    return False


def get_least_cold(models: list[str]) -> str:
    """Return the model with the shortest remaining cooldown — used when all fallbacks are cooling down."""
    now = time.time()
    return min(models, key=lambda m: _cooldowns.get(m, now))


def get_status() -> dict[str, float]:
    """Return {model_id: remaining_cooldown_secs} for all currently unhealthy models."""
    now = time.time()
    expired = [m for m, until in _cooldowns.items() if until <= now]
    for m in expired:
        del _cooldowns[m]
    return {m: round(until - now, 1) for m, until in _cooldowns.items()}
