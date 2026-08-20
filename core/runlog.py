"""Shared logging seam for background work.

Every module in core/ used to define its own `def log(msg): print(msg, flush=True)`,
which meant all operational output went to the uvicorn console and nowhere the UI
could reach it. This module keeps that exact call signature — so call sites are
unchanged — but fans the message out three ways:

  1. stdout, as before (the console still works)
  2. an in-memory ring buffer, for the global log tail in the UI
  3. the `run_logs` table, when a run context is active

The run context is a contextvar, so `run_id` does not have to be threaded through
every function signature in the collector/emailer call graph.
"""

from __future__ import annotations

import contextvars
import threading
from collections import deque
from datetime import datetime

# Global tail — what the UI shows when no specific run is selected.
_RING_MAX = 500
_ring: deque = deque(maxlen=_RING_MAX)
_ring_lock = threading.Lock()

# Active run for the current task/thread. None = not inside a run.
_current_run: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_run_id", default=None
)


def set_run_context(run_id: int | None) -> contextvars.Token:
    """Bind subsequent log() calls in this task to a run. Returns a reset token."""
    return _current_run.set(run_id)


def reset_run_context(token: contextvars.Token) -> None:
    _current_run.reset(token)


def current_run_id() -> int | None:
    return _current_run.get()


def log(msg: str, level: str = "info") -> None:
    """Drop-in replacement for the old per-module log(). Never raises —
    a logging failure must not abort a collection run."""
    text = str(msg)
    ts = datetime.utcnow().isoformat()

    try:
        print(text, flush=True)
    except Exception:
        pass

    entry = {"ts": ts, "level": level, "message": text, "run_id": _current_run.get()}
    with _ring_lock:
        _ring.append(entry)

    run_id = _current_run.get()
    if run_id is not None:
        try:
            from core.database import insert_run_log
            insert_run_log(run_id, level, text)
        except Exception:
            # Log persistence is best-effort; stdout already has it.
            pass


def warn(msg: str) -> None:
    log(msg, level="warn")


def error(msg: str) -> None:
    log(msg, level="error")


def progress(current: int, total: int, label: str = "") -> None:
    """Report progress for the active run. No-op outside a run context."""
    run_id = _current_run.get()
    if run_id is None:
        return
    try:
        from core.database import update_run_progress
        update_run_progress(run_id, current, total, label)
    except Exception:
        pass


def tail(limit: int = 200, level: str | None = None) -> list[dict]:
    """Most recent log lines, newest last (chronological, as a console reads)."""
    with _ring_lock:
        items = list(_ring)
    if level:
        items = [e for e in items if e["level"] == level]
    return items[-limit:]


def clear() -> None:
    """Test helper."""
    with _ring_lock:
        _ring.clear()
