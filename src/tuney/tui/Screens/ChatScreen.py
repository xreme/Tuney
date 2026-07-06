import asyncio

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Input, Header, Footer, Static, Button, Markdown
from textual.containers import VerticalScroll, Horizontal, Vertical
from tuney import config
from textual import work


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
        yield Markdown(self._text, classes=f"bubble {self._role}")


class ChatScreen(Screen):
    """Access Tuney AI agent"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("ctrl+s", "swap", "Swap view"),
        ("q", "quit", "Quit"),
    ]

    CSS_PATH = "ChatScreen.tcss"

    def compose(self) -> ComposeResult:
        yield Header()

        with Vertical(id="focus-view"):
            with Horizontal(id="topbar"):
                yield Button("-", id="swap", variant="success")
            with Vertical(id="dialog"):
                yield Static(id="dialog-spacer")
                yield Static(MASCOT, id="mascot")
                with VerticalScroll(id="ai-reply-scroll"):
                    yield Markdown("Hi, I'm Tuney! How can I help you?", id="ai-reply")
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
        if config.get_config().tui_chat_view == config.ChatView.HISTORY:
            self.action_swap()
        self.query_one(Input).focus()
        self.call_after_refresh(self._cap_reply)

    def on_resize(self) -> None:
        self._cap_reply()

    def _cap_reply(self) -> None:
        """Cap the reply panel's height so it hugs short replies but never grows
        far enough to push the user's query off-screen. The panel scrolls
        internally once a reply exceeds the available space."""
        scroll = self.query_one("#ai-reply-scroll")
        if not scroll.region:                       # not laid out yet
            return
        dialog_height = self.query_one("#dialog").region.height
        query_height = self.query_one("#user-query").region.height
        # The spacer bottom-anchors the whole mascot + reply + query group, so
        # positions shift as the reply grows; work from heights instead. The
        # mascot's 1-line bottom margin isn't in its region, and Textual never
        # resolves a 1fr widget below 1 row, so reserve a row for the spacer
        # too or the query gets pushed a line past the dialog.
        mascot_height = self.query_one("#mascot").region.height + 1
        available = dialog_height - mascot_height - query_height - 1
        scroll.styles.max_height = max(3, available)

    # ---- view toggling ----------------------------------------------------

    def action_swap(self) -> None:
        self.query_one("#focus-view").toggle_class("hidden")
        self.query_one("#history-view").toggle_class("hidden")
        focus_hidden = self.query_one("#focus-view").has_class("hidden")
        cfg = config.get_config()
        cfg.tui_chat_view = (config.ChatView.HISTORY if focus_hidden else config.ChatView.FOCUS)
        cfg.save()

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
        self._set_focus_exchange(query=text, reply="Thinking...")
        self._append_history(text, "user")
        self._run_query(text)

    THINKING_TAIL_CHARS = 300

    @work(exclusive = True)
    async def _run_query(self, text: str):
        from tuney.agents.collectionSearchAgent import collection_search_agent

        reply = self.query_one("#ai-reply", Markdown)
        scroll = self.query_one("#ai-reply-scroll")
        parts: list[str] = []
        thinking: list[str] = []
        stream = None

        async def _stream():
            nonlocal stream
            if stream is None:
                await reply.update("")
                stream = Markdown.get_stream(reply)
            return stream

        async def _show_thinking():
            trace = "".join(thinking)
            tail = trace[-self.THINKING_TAIL_CHARS:]
            if len(trace) > self.THINKING_TAIL_CHARS:
                # Cut at a word boundary so the tail doesn't open mid-word.
                tail = "…" + tail.split(" ", 1)[-1]
            quoted = "\n".join(f"> {line}" for line in tail.splitlines())
            await reply.update(f"Thinking...\n\n{quoted}")

        try:
            async for kind, token in collection_search_agent.astream(text):
                if kind == "reasoning":
                    if stream is None:      # answer hasn't started yet
                        thinking.append(token)
                        await _show_thinking()
                    continue
                parts.append(token)
                await (await _stream()).write(token)
                scroll.scroll_end(animate=False)    # follow the incoming text
        except asyncio.CancelledError:
            # Worker cancelled (new query submitted, screen closed). Keep any
            # partial reply in history instead of losing it silently; no
            # awaits here — the task is already being torn down.
            if parts:
                self._append_history("".join(parts) + "\n\n*(interrupted)*", "ai")
            raise
        except Exception as e:
            parts.append(f"\n\n**[error]** {e}")
            await (await _stream()).write(parts[-1])

        if stream is not None:
            await stream.stop()

        # stream finished — the AI is done responding
        final = "".join(parts)
        if not final:
            await reply.update("(no response)")
            final = "(no response)"
        self._append_history(final, "ai")

    def _set_focus_exchange(self, query: str, reply: str) -> None:
        """Replace the latest exchange shown in the focus view."""
        self.query_one("#ai-reply", Markdown).update(reply)
        self.query_one("#user-query", Static).update(query)
        self.query_one("#ai-reply-scroll").scroll_home(animate=False)
        # The query height may have changed (wrapping); re-cap the reply panel.
        self.call_after_refresh(self._cap_reply)

    def _append_history(self, text: str, role: str) -> None:
        """Append to the full scrolling conversation view."""
        history = self.query_one("#history-scroll", VerticalScroll)
        history.mount(Message(text, role))
        history.scroll_end(animate=False)

    def action_back(self) -> None:
        self.app.pop_screen()
