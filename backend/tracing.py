"""
Omium tracing integration for omniBox.

Span hierarchy for a goal:
  goal_run  (execution_id = goal.trace_id)
    └─ orchestrator_plan
    └─ task/researcher  (task_id=t1)
         └─ tool/web_search
         └─ tool/web_search  (idempotent replay — tagged cached=true)
    └─ task/writer  (task_id=t2)
         └─ tool/file_ops
    └─ webhook_resume  (when a WAITING_WEBHOOK task is resumed via POST /webhooks)

All spans share the same execution_id (= goal.trace_id) so judges see
one unified trace per goal in the Omium dashboard — causal chain intact.
"""
import contextlib
import logging
import os
from contextvars import ContextVar
from typing import Any, Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

_omium_available = False
_OmiumTracer = None  # type: ignore
_omium_ctx_var: Optional[ContextVar] = None

try:
    import omium as _omium_module
    from omium.integrations.tracer import OmiumTracer as _OmiumTracer, _current_tracer as _omium_ctx_var
    _omium_available = True
except ImportError:
    logger.warning("omium not installed — tracing disabled. pip install omium to enable.")
except Exception as e:
    logger.warning("omium import error — tracing disabled: %s", e)


# ── Initialisation ────────────────────────────────────────────────────────────

def init_tracing(api_key: str, project: str) -> None:
    global _omium_available
    if not _omium_available:
        return
    if not api_key:
        logger.info("OMIUM_API_KEY not set — tracing disabled")
        return
    try:
        if settings.omium_skip_workflow_register:
            os.environ.setdefault("OMIUM_SKIP_WORKFLOW_REGISTER", "true")
        _omium_module.init(
            api_key=api_key,
            project=project,
            auto_trace=False,       # manual instrumentation for full control
            auto_checkpoint=False,
        )
        logger.info("Omium tracing initialised (project=%s)", project)
    except Exception as e:
        logger.warning("Omium init failed: %s — tracing disabled", e)
        _omium_available = False


# ── Per-goal tracer context ───────────────────────────────────────────────────

@contextlib.contextmanager
def goal_trace_context(execution_id: str, goal_title: str):
    """
    Context manager that creates an OmiumTracer scoped to one goal.
    All child spans (orchestrator, tasks, tools) share the same execution_id
    so they appear as one causally-linked trace in the Omium dashboard.
    """
    if not _omium_available or _OmiumTracer is None or _omium_ctx_var is None:
        yield None
        return

    tracer = _OmiumTracer(execution_id=execution_id, trace_id=execution_id)
    token = _omium_ctx_var.set(tracer)
    try:
        with tracer.span(
            "goal_run",
            input={"goal": goal_title},
            span_type="agent",
            goal_id=execution_id,
        ) as root_span:
            root_span.set_attribute("omnibox.component", "orchestrator")
            yield tracer
            root_span.add_event("goal_finished")
    finally:
        _omium_ctx_var.reset(token)
        _flush_tracer(tracer)


@contextlib.contextmanager
def task_span(tracer: Any, task_id: str, agent_name: str, description: str):
    """Span for a single agent task execution (child of goal_run)."""
    if tracer is None:
        yield None
        return
    with tracer.span(
        f"task/{agent_name}",
        input={"task_id": task_id, "description": description},
        span_type="agent",
        task_id=task_id,
        agent=agent_name,
        omnibox_component="task_executor",
    ) as span:
        yield span


@contextlib.contextmanager
def tool_span(tracer: Any, task_id: str, tool_name: str, args: dict, cached: bool = False):
    """Span for a single tool call (child of task span)."""
    if tracer is None:
        yield None
        return
    with tracer.span(
        f"tool/{tool_name}",
        input={"task_id": task_id, **_truncate_args(args)},
        span_type="tool",
        task_id=task_id,
        tool=tool_name,
        cached=cached,
        omnibox_component="tool_executor",
    ) as span:
        yield span


@contextlib.contextmanager
def webhook_span(tracer: Any, task_id: str, wait_token: str, payload: dict):
    """Span for an inbound webhook that resumes a suspended task."""
    if tracer is None:
        yield None
        return
    with tracer.span(
        "webhook_resume",
        input={"task_id": task_id, "wait_token": wait_token[:16] + "…", "payload": payload},
        span_type="tool",
        task_id=task_id,
        event="webhook_fire",
        omnibox_component="webhook_receiver",
    ) as span:
        yield span


# ── @trace decorator (used on orchestrator, agent_runner) ─────────────────────

def trace(name: str) -> Callable:
    """
    Decorator that wraps an async/sync function with an Omium span.
    Falls back to the raw function if omium is not available.
    """
    def decorator(fn: Callable) -> Callable:
        if not _omium_available:
            return fn
        try:
            return _omium_module.trace(
                name,
                span_type="agent",
                capture_input=True,
                capture_output=True,
            )(fn)
        except Exception:
            return fn
    return decorator


def checkpoint(name: str) -> Callable:
    """Decorator that records a named checkpoint event in the current span."""
    def decorator(fn: Callable) -> Callable:
        if not _omium_available:
            return fn
        try:
            return _omium_module.checkpoint(name, on_error="log")(fn)
        except Exception:
            return fn
    return decorator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate_args(args: dict, max_str: int = 300) -> dict:
    out = {}
    for k, v in args.items():
        if k.startswith("_"):
            continue
        if isinstance(v, str) and len(v) > max_str:
            out[k] = v[:max_str] + "…"
        else:
            out[k] = v
    return out


def get_active_tracer() -> Optional[Any]:
    """Return the OmiumTracer active in this asyncio task, or None."""
    if not _omium_available or _omium_ctx_var is None:
        return None
    try:
        return _omium_ctx_var.get()
    except Exception:
        return None


def _flush_tracer(tracer: Any) -> None:
    """Fire-and-forget flush — uses asyncio if a loop is running."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(tracer.aflush())
        else:
            tracer.flush()
    except Exception:
        try:
            tracer.flush()
        except Exception:
            pass


# ── Legacy stubs (imported by orchestrator / agent_runner) ────────────────────

def set_execution_context(execution_id: str, agent_id: str) -> None:
    """No-op — context is now managed via goal_trace_context."""
    pass


def get_client() -> Any:
    """Legacy — returns None."""
    return None
