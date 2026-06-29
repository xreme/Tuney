from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Input, Header, Footer, Static
from textual.containers import VerticalScroll, Horizontal


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
        ("q", "quit", "Quit"),
    ]

    CSS = """
        #messages {
            height: 1fr;
            align-vertical: bottom;
        }
        .row {
            height: auto;
            width: 1fr;
        }
        .row.user {
            align-horizontal: right;
        }
        .row.ai {
            align-horizontal: left;
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
        }
        .bubble.ai {
            background: $panel;
            color: $text;
        }
        """

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="messages")
        yield Input(placeholder="Say something", id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def add_message(self, text: str, role: str) -> None:
        messages = self.query_one("#messages", VerticalScroll)
        messages.mount(Message(text, role))
        messages.scroll_end(animate=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.add_message(text, "user")
        event.input.value = ""
        # Placeholder AI reply — swap in the real agent here.
        self.add_message("…", "ai")

    def action_back(self) -> None:
        self.app.pop_screen()
