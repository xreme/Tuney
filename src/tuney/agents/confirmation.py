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


def set_confirmation_handler(handler: ConfirmationHandler | None) -> None:
    """Register the UI's confirmation dialog. Pass None to unregister."""
    global _handler
    _handler = handler


async def confirm(action_requests: list) -> list[dict]:
    """Ask the registered UI to decide each request; reject all if no UI."""
    if _handler is None:
        return [
            {"type": "reject", "message": "No confirmation UI is available."}
            for _ in action_requests
        ]
    return await _handler(action_requests)
