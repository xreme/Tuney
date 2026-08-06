"""Live registry of specialist (subagent) runs, for the UI to display.

The supervisor registers each delegation while it runs; the chat pane's
subagent panel polls `snapshot()` to show what's in flight.
"""

import itertools
import threading
import time
from contextlib import contextmanager

_ids = itertools.count(1)
_active: dict[int, dict] = {}

_long_tasks = 0
_long_completed = 0
_long_lock = threading.Lock()

_changes = 0
_change_lock = threading.Lock()


@contextmanager
def long_task():
    """Mark a slow, non-streaming tool call as running for its duration."""
    global _long_tasks, _long_completed
    with _long_lock:
        _long_tasks += 1
    try:
        yield
    finally:
        with _long_lock:
            _long_tasks -= 1
            _long_completed += 1


def busy() -> bool:
    """True while a tool marked with `long_task` is running."""
    with _long_lock:
        return _long_tasks > 0


def completed_long_tasks() -> int:
    """How many `long_task` blocks have finished since the process started."""
    with _long_lock:
        return _long_completed


def record_change() -> None:
    """Note that a tool changed something. Call it once per tool call, and only
    when something really landed."""
    global _changes
    with _change_lock:
        _changes += 1


def recorded_changes() -> int:
    """How many changes tools have recorded since the process started."""
    with _change_lock:
        return _changes


def start(agent: str, task: str) -> int:
    """Record a delegation starting; returns a token for `finish`."""
    token = next(_ids)
    _active[token] = {"agent": agent, "task": task, "started": time.monotonic(),
                      "tool": ""}
    return token


def set_tool(token: int, tool: str) -> None:
    """Note which of its own tools a running specialist is calling now (empty
    string once the result is back)."""
    run = _active.get(token)
    if run is not None:
        run["tool"] = tool


def finish(token: int) -> None:
    _active.pop(token, None)


def snapshot() -> list[dict]:
    """Active runs, oldest first, each with an `elapsed` seconds field."""
    now = time.monotonic()
    return [dict(info, elapsed=now - info["started"])
            for info in _active.values()]
