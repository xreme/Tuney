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

# Consulted by the agent's stream-inactivity watchdog, so a transcode or a
# bulk retag isn't mistaken for the AI service going silent.
_long_tasks = 0
_long_lock = threading.Lock()


@contextmanager
def long_task():
    """Mark a slow, non-streaming tool call as running for its duration. Tools
    may execute on worker threads, hence the lock."""
    global _long_tasks
    with _long_lock:
        _long_tasks += 1
    try:
        yield
    finally:
        with _long_lock:
            _long_tasks -= 1


def busy() -> bool:
    """True while a tool marked with `long_task` is running."""
    with _long_lock:
        return _long_tasks > 0


def start(agent: str, task: str) -> int:
    """Record a delegation starting; returns a token for `finish`."""
    token = next(_ids)
    _active[token] = {"agent": agent, "task": task, "started": time.monotonic()}
    return token


def finish(token: int) -> None:
    _active.pop(token, None)


def snapshot() -> list[dict]:
    """Active runs, oldest first, each with an `elapsed` seconds field."""
    now = time.monotonic()
    return [dict(info, elapsed=now - info["started"])
            for info in _active.values()]
