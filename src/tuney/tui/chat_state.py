"""Module-level chat transcript store.

The workspace rebuilds pane widgets when the layout changes, so the chat
pane can't own its transcript — it lives here and the pane replays it on
mount. One conversation per app run (matching the single shared agent).
"""

messages: list[list[str]] = []          # [role, text] in order
focus_exchange: list[str] | None = None  # [query, reply] shown in the focus view


def add(role: str, text: str) -> int:
    """Append a message; returns its index for later updates."""
    messages.append([role, text])
    return len(messages) - 1


def update(index: int, text: str) -> None:
    messages[index][1] = text


def set_focus(query: str, reply: str) -> None:
    global focus_exchange
    focus_exchange = [query, reply]
