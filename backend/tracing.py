"""
Omium tracing integration. Falls back to no-ops if omium is not installed.
Stores trace_id in DB so workers reconstitute causal context after restart.
"""
import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_client = None
_omium_available = False

try:
    import omium as _omium_module
    _omium_available = True
except ImportError:
    logger.warning("omium not installed — tracing disabled. pip install omium to enable.")


def init_tracing(api_key: str, project: str) -> None:
    global _client, _omium_available
    if not _omium_available or not api_key:
        return
    try:
        _omium_module.init(api_key=api_key, project=project)
        _client = _omium_module.OmiumClient(api_key=api_key)
        logger.info("Omium tracing initialized (project=%s)", project)
    except Exception as e:
        logger.warning("Omium init failed: %s — tracing disabled", e)
        _omium_available = False


def get_client() -> Any:
    return _client


def set_execution_context(execution_id: str, agent_id: str) -> None:
    if _client is None:
        return
    try:
        _client.set_execution_context(execution_id=execution_id, agent_id=agent_id)
    except Exception:
        pass


def trace(name: str) -> Callable:
    """Decorator: wraps async or sync function with an Omium trace span."""
    def decorator(fn: Callable) -> Callable:
        if not _omium_available:
            return fn
        try:
            return _omium_module.trace(name)(fn)
        except Exception:
            return fn
    return decorator


def checkpoint(name: str) -> Callable:
    """Decorator: wraps async function with an Omium checkpoint."""
    def decorator(fn: Callable) -> Callable:
        if not _omium_available:
            return fn
        try:
            return _omium_module.checkpoint(name)(fn)
        except Exception:
            return fn
    return decorator
