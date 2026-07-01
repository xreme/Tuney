from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Input, Header, Footer, Static, Button
from textual.containers import VerticalScroll, Horizontal, Vertical
from tuney import config


MASCOT = r"""
 ┌────────┐
 │  O  O  │
 │   ◡    │
"""


class Message(Horizontal):
    """A single chat message row, aligned by sender."""

    def __init__(self, text: str, role: str) -> None:
        super().__init__(classes=f"row {role}")
        self._text = text
        self._role = role

    def compose(self) -> ComposeResult:
        yield Static(self._text, classes=f"bubble {self._role}")


class ChatScreen(Screen):
    """Access Tuney AI agent"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("ctrl+s", "swap", "Swap view"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
        /* ---- Focus view (mascot + latest exchange) ---- */
        #focus-view {
            height: 1fr;
            padding: 1 2;
        }
        #topbar {
            height: auto;
            align-horizontal: right;
        }
        #mascot {
            width: 1fr;
            height: auto;
            text-align: center;
            margin-bottom: 1;
        }
        #dialog {
            # background: black;
            align-vertical: bottom;
        }
        #ai-reply {
            width: 1fr;
            height: auto;
            max-height: 1fr;
            overflow-y: auto;
            padding: 1 2;
            background: #7fb3e8;
            color: black;
        }
        #user-query {
            width: 1fr;
            height: auto;
            min-height: 3;
            padding: 1 2;
            text-align: center;
            background: grey;
            color: black;
        }

        /* ---- History view (full scrolling conversation) ---- */
        #history-view {
            height: 1fr;
            padding: 1 2;
        }
        #history-topbar {
            height: auto;
            align-horizontal: right;
        }
        #history-scroll {
            height: 1fr;
            align-vertical: bottom;
        }
        .row {
            height: auto;
            width: 1fr;
            align-horizontal: center;
        }
        .bubble {
            width: auto;
            max-width: 80%;
            padding: 1 2;
            margin: 1 0;
        }
        .bubble.user {
            background: $primary;
            color: $text;
            align-horizontal: left;
        }
        .bubble.ai {
            background: $panel;
            color: $text;
            align-horizontal: right;
        }

        /* ---- Composer ---- */
        #composer {
            height: auto;
        }
        #input {
            width: 1fr;
        }
        #send {
            min-width: 5;
        }

        .hidden {
            display: none;
        }
        """

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="focus-view"):
            with Horizontal(id="topbar"):
                yield Button("-", id="swap", variant="success")
            with Vertical(id="dialog"):
                yield Static(MASCOT, id="mascot")
                yield Static("Hi, I'm Tuney! How can I help you?", id="ai-reply")
                yield Static("", id="user-query")

        with Vertical(id="history-view", classes="hidden"):
            with Horizontal(id="history-topbar"):
                yield Button("-", id="swap-back", variant="success")
            yield VerticalScroll(id="history-scroll")

        with Horizontal(id="composer"):
            yield Input(placeholder="Say something", id="input")
            yield Button("↑", id="send", variant="primary")

        yield Footer()

    def on_mount(self) -> None:
        if config.load_config()["tui_chat_view"] == "history":
            self.action_swap()
        self.query_one(Input).focus()

    # ---- view toggling ----------------------------------------------------

    def action_swap(self) -> None:
        self.query_one("#focus-view").toggle_class("hidden")
        self.query_one("#history-view").toggle_class("hidden")
        focus_hidden = self.query_one("#focus-view").has_class("hidden")
        config.write_config("tui_chat_view",  "history" if focus_hidden else "focus")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("swap", "swap-back"):
            self.action_swap()
        elif event.button.id == "send":
            self._submit(self.query_one(Input).value)

    # ---- messaging --------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value)

    def _submit(self, value: str) -> None:
        text = value.strip()
        if not text:
            return
        self.query_one(Input).value = ""

        reply = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."

        self._set_focus_exchange(query=text, reply=reply)
        self._append_history(text, "user")
        self._append_history(reply, "ai")

    def _set_focus_exchange(self, query: str, reply: str) -> None:
        """Replace the latest exchange shown in the focus view."""
        self.query_one("#ai-reply", Static).update(reply)
        self.query_one("#user-query", Static).update(query)

    def _append_history(self, text: str, role: str) -> None:
        """Append to the full scrolling conversation view."""
        history = self.query_one("#history-scroll", VerticalScroll)
        history.mount(Message(text, role))
        history.scroll_end(animate=False)

    def action_back(self) -> None:
        self.app.pop_screen()
