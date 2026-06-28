from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Input, Header, Footer, Static
from textual.containers import VerticalScroll

class ChatScreen(Screen):
    """Access Tuney AI agent"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
        #messages {
            height: 1fr;
        }
        """

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="messages")
        yield Input(placeholder="Say something", id="input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        messages = self.query_one("#messages", VerticalScroll)
        messages.mount(Static(f"You: {text}"))
        event.input.value = ""
        messages.scroll_end(animate=False)
    def action_back(self) -> None:
        self.app.pop_screen()
