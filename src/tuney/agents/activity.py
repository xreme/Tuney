"""Live registry of specialist (subagent) runs, for the UI to display.

The supervisor registers each delegation while it runs; the chat pane's
subagent panel polls `snapshot()` to show what's in flight.
"""

import itertools
import time

_ids = itertools.count(1)
_active: dict[int, dict] = {}


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
