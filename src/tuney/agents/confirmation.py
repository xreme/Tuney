"""Bridge between agents that need user confirmation and whatever UI is active.

Specialist agents pause on destructive tool calls (HumanInTheLoopMiddleware).
When a specialist runs nested inside a supervisor's tool call, its pause can't
surface as a graph interrupt of the supervisor, so the delegation layer asks
the active UI directly through the handler registered here.
"""

from collections.abc import Awaitable, Callable

# Takes the action requests surfaced by HumanInTheLoopMiddleware
# ([{"name", "args", "description"}, ...]) and returns one decision per
# request, in the same order: {"type": "approve"} or
# {"type": "reject", "message": ...}.
ConfirmationHandler = Callable[[list], Awaitable[list[dict]]]

_handler: ConfirmationHandler | None = None

# How many confirmation prompts are currently awaiting the user. The agent's
# stream-inactivity watchdog checks this so it doesn't mistake "the user is
# deciding on a dialog" for "the AI service went silent" — a mass removal can
# put many dialogs in front of the user and easily outlast that window.
_pending = 0


def set_confirmation_handler(handler: ConfirmationHandler | None) -> None:
    """Register the UI's confirmation dialog. Pass None to unregister."""
    global _handler
    _handler = handler


def is_pending() -> bool:
    """True while the user is being asked to confirm one or more tool calls."""
    return _pending > 0


async def confirm(action_requests: list) -> list[dict]:
    """Ask the registered UI to decide each request; reject all if no UI."""
    if _handler is None:
        return [
            {"type": "reject", "message": "No confirmation UI is available."}
            for _ in action_requests
        ]
    global _pending
    _pending += 1
    try:
        return await _handler(action_requests)
    finally:
        _pending -= 1
