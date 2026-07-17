import asyncio
import dataclasses
from time import monotonic

from textual.binding import Binding
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Input, Header, Footer, Static, Button, Markdown
from textual.containers import VerticalScroll, Horizontal, Vertical
from tuney import config
from tuney.tui.Modals import ConfirmModal
from textual import work


MASCOT = r"""
   ┌────────┐
   │  O  O  │
   │   ◡    │
   │        │
 (_)      (_)
"""


class Message(Horizontal):
    """A single chat message row, aligned by sender."""

    def __init__(self, text: str, role: str) -> None:
        super().__init__(classes=f"row {role}")
        self.markdown = Markdown(text, classes=f"bubble {role}")

    def compose(self) -> ComposeResult:
        yield self.markdown


class ChatScreen(Screen):
    """Access Tuney AI agent"""

    BINDINGS = [
        ("escape", "back", "Back to menu"),
        ("ctrl+s", "swap", "Swap view"),
        # Priority so it wins over the focused Input's own ctrl+d binding.
        Binding("ctrl+d", "cycle_detail", "Detail", priority=True),
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
                yield Static("", id="stopwatch", classes="hidden")
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
        self._stopwatch_timer = None
        self._stopwatch_gen = 0
        self._stopwatch_start = 0.0
        if config.get_config().tui_chat_view == config.ChatView.HISTORY:
            self.action_swap()
        self._update_detail_indicator()
        self.query_one(Input).focus()
        self.call_after_refresh(self._cap_reply)

    def on_screen_resume(self) -> None:
        self._update_detail_indicator()

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
        # Hidden widgets have an empty region, so this is 0 when idle.
        stopwatch_height = self.query_one("#stopwatch").region.height
        available = dialog_height - mascot_height - stopwatch_height - query_height - 1
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

    # ---- chat detail -------------------------------------------------------

    def action_cycle_detail(self) -> None:
        levels = list(config.ChatDetail)
        cfg = config.get_config()
        cfg.chat_detail = levels[(levels.index(cfg.chat_detail) + 1) % len(levels)]
        cfg.save()
        self._update_detail_indicator()

    def _update_detail_indicator(self) -> None:
        """Show the current level in the footer as `^d Detail: <level>` by
        rewriting the binding's description in place."""
        detail = config.get_config().chat_detail
        self._bindings.key_to_bindings["ctrl+d"] = [
            dataclasses.replace(b, description=f"Detail: {detail}")
            for b in self._bindings.key_to_bindings["ctrl+d"]
        ]
        self.refresh_bindings()

    # ---- stopwatch ---------------------------------------------------------
    # One agent run at a time owns the stopwatch. The generation token makes
    # a cancelled run's cleanup a no-op once a newer run has taken over, so
    # the display never vanishes mid-run.

    def _start_stopwatch(self) -> int:
        self._stopwatch_gen += 1
        self._stopwatch_start = monotonic()
        if self._stopwatch_timer is not None:
            self._stopwatch_timer.stop()
        self._stopwatch_timer = self.set_interval(0.1, self._update_stopwatch)
        self.query_one("#stopwatch", Static).remove_class("hidden")
        self._update_stopwatch()
        # The stopwatch line takes a row from the dialog; re-cap the reply.
        self.call_after_refresh(self._cap_reply)
        return self._stopwatch_gen

    def _update_stopwatch(self) -> None:
        elapsed = monotonic() - self._stopwatch_start
        self.query_one("#stopwatch", Static).update(f"⏱ {elapsed:.1f}s")

    def _stop_stopwatch(self, gen: int) -> None:
        if gen != self._stopwatch_gen:
            return
        if self._stopwatch_timer is not None:
            self._stopwatch_timer.stop()
            self._stopwatch_timer = None
        self.query_one("#stopwatch", Static).add_class("hidden")
        self.call_after_refresh(self._cap_reply)

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
        live = self._append_history("Thinking...", "ai")
        self._run_query(text, live)

    THINKING_TAIL_CHARS = 300

    async def _confirm(self, requests: list) -> list[dict]:
        """Show the confirmation dialog for each pending tool call, in order.

        Registered as the agents' confirmation handler, so specialists paused
        deep inside a supervisor delegation still reach the user's modal.
        """
        decisions = []
        for request in requests:
            approved = await self.app.push_screen_wait(ConfirmModal(request))
            decisions.append(
                {"type": "approve"} if approved
                else {"type": "reject",
                      "message": "The user declined this action."}
            )
        return decisions

    @work(exclusive = True)
    async def _run_query(self, text: str, live: Message):
        from tuney.agents.confirmation import set_confirmation_handler
        from tuney.agents.supervisor import tuney_agent

        set_confirmation_handler(self._confirm)
        stopwatch = self._start_stopwatch()

        reply = self.query_one("#ai-reply", Markdown)
        scroll = self.query_one("#ai-reply-scroll")
        history = self.query_one("#history-scroll", VerticalScroll)
        hist_md = live.markdown
        parts: list[str] = []
        thinking: list[str] = []
        streams: list = []

        async def _streams():
            if not streams:
                await reply.update("")
                await hist_md.update("")
                streams.append(Markdown.get_stream(reply))
                streams.append(Markdown.get_stream(hist_md))
            return streams

        async def _show_thinking():
            trace = "".join(thinking)
            tail = trace[-self.THINKING_TAIL_CHARS:]
            if len(trace) > self.THINKING_TAIL_CHARS:
                # Cut at a word boundary so the tail doesn't open mid-word.
                tail = "…" + tail.split(" ", 1)[-1]
            quoted = "\n".join(f"> {line}" for line in tail.splitlines())
            status = f"Thinking...\n\n{quoted}"
            await reply.update(status)
            await hist_md.update(status)
            history.scroll_end(animate=False)

        async def _render(events) -> list | None:
            """Render one agent stream; return the interrupt requests if the
            run paused for tool confirmation, else None when it finished."""
            requests = None
            async for kind, token in events:
                if kind == "interrupt":
                    requests = token        # stream ends right after; dialog comes then
                    continue
                if kind == "reasoning":
                    if not streams:         # answer hasn't started yet
                        thinking.append(token)
                        await _show_thinking()
                    continue
                parts.append(token)
                for s in await _streams():
                    await s.write(token)
                scroll.scroll_end(animate=False)    # follow the incoming text
                history.scroll_end(animate=False)
            return requests

        try:
            pending = await _render(tuney_agent.astream(text))
            while pending:
                # The supervisor itself has no confirmable tools today —
                # specialist confirmations arrive via the handler registered
                # above — but handle a top-level interrupt all the same.
                pending = await _render(tuney_agent.aresume(await self._confirm(pending)))
        except asyncio.CancelledError:
            # Worker cancelled (new query submitted, screen closed). Keep any
            # partial reply in its history bubble instead of losing it
            # silently; no awaits here — the task is already being torn down,
            # and Markdown.update runs without being awaited.
            partial = "".join(parts)
            hist_md.update(f"{partial}\n\n*(interrupted)*" if partial
                           else "*(interrupted)*")
            raise
        except Exception as e:
            parts.append(f"\n\n**[error]** {e}")
            for s in await _streams():
                await s.write(parts[-1])
        finally:
            # Sync-only: on cancellation the task is already being torn down.
            self._stop_stopwatch(stopwatch)

        for s in streams:
            await s.stop()

        # stream finished — the AI is done responding
        if not parts:
            await reply.update("(no response)")
            await hist_md.update("(no response)")
        history.scroll_end(animate=False)

    def _set_focus_exchange(self, query: str, reply: str) -> None:
        """Replace the latest exchange shown in the focus view."""
        self.query_one("#ai-reply", Markdown).update(reply)
        self.query_one("#user-query", Static).update(query)
        self.query_one("#ai-reply-scroll").scroll_home(animate=False)
        # The query height may have changed (wrapping); re-cap the reply panel.
        self.call_after_refresh(self._cap_reply)

    def _append_history(self, text: str, role: str) -> Message:
        """Append to the full scrolling conversation view."""
        history = self.query_one("#history-scroll", VerticalScroll)
        message = Message(text, role)
        history.mount(message)
        history.scroll_end(animate=False)
        return message

    def action_back(self) -> None:
        self.app.pop_screen()
