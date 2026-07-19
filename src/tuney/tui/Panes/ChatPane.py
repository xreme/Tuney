import asyncio
import dataclasses
from time import monotonic

from textual.binding import Binding
from textual.css.query import NoMatches
from textual.message import Message as TextualMessage
from textual.app import ComposeResult
from textual.widgets import Input, Static, Button, Markdown
from textual.containers import VerticalScroll, Horizontal, Vertical
from tuney import config
from tuney.tui import chat_state
from tuney.tui.Modals import ConfirmModal
from textual import work
from .base import Pane


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
        self.state_index: int | None = None    # position in chat_state.messages

    def compose(self) -> ComposeResult:
        yield self.markdown


class ChatPane(Pane):
    """Access Tuney AI agent"""

    PANE_NAME = "Chat"

    class AgentRunFinished(TextualMessage):
        """An agent run just ended — it may have changed the library."""

    BINDINGS = [
        ("ctrl+s", "swap", "Swap view"),
        Binding("ctrl+d", "cycle_detail", "Detail", priority=True),
    ]

    DEFAULT_CSS = """
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
        height: 1fr;
    }
    #dialog-spacer {
        /* Absorbs the leftover space so the mascot + reply + query sit at
           the bottom of the dialog, just above the input. */
        height: 1fr;
    }
    #ai-reply-scroll {
        width: 1fr;
        height: auto;      /* hug the reply; max-height is capped in code */
        background: $panel;
    }
    #ai-reply {
        width: 1fr;
        height: auto;
        padding: 1 2;
        color: $text;
    }
    #user-query {
        width: 1fr;
        height: auto;
        min-height: 3;
        padding: 1 2;
        text-align: center;
        background: $primary;
        color: $text;
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
    #subagent-panel {
        height: auto;
        max-height: 8;
        margin: 0 2 1 2;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
        border-left: thick $accent;
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
        width: 1fr;
        max-width: 80%;
        background: $panel;
        color: $text;
        align-horizontal: right;
    }
    /* Markdown adds its own vertical margins; trim them inside a bubble. */
    .bubble.ai > * {
        margin: 0;
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

    /* ---- Stopwatch (visible while an agent run is in flight) ---- */
    #stopwatch {
        height: 1;
        padding: 0 2;
        text-align: left;
        color: $text-muted;
    }

    .hidden {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
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

        # Live subagent activity and the run stopwatch sit just above the
        # composer; both are visible in either view and collapse when idle.
        yield Static("", id="subagent-panel", classes="hidden")
        yield Static("", id="stopwatch", classes="hidden")

        with Horizontal(id="composer"):
            yield Input(placeholder="Say something", id="input")
            yield Button("↑", id="send", variant="primary")

    def on_mount(self) -> None:
        self._stopwatch_timer = None
        self._stopwatch_gen = 0
        self._stopwatch_start = 0.0
        self._approve_all = False
        self._reject_all = False
        if config.get_config().tui_chat_view == config.ChatView.HISTORY:
            self.action_swap()
        self._replay_transcript()
        self._update_detail_indicator()
        self.set_interval(0.5, self._update_subagents)
        self.call_after_refresh(self._cap_reply)

    def _replay_transcript(self) -> None:
        """Restore the conversation so far — the transcript outlives this
        widget across layout rebuilds. Mounted as one batch with a single
        scroll: mounting each message separately relays out the history per
        message, which makes rebuilding a pane with a long chat visibly lag."""
        messages = []
        for index, (role, text) in enumerate(chat_state.messages):
            message = Message(text, role)
            message.state_index = index
            messages.append(message)
        if messages:
            history = self.query_one("#history-scroll", VerticalScroll)
            history.mount_all(messages)
            history.scroll_end(animate=False)
        if chat_state.focus_exchange is not None:
            query, reply = chat_state.focus_exchange
            self.query_one("#ai-reply", Markdown).update(reply)
            self.query_one("#user-query", Static).update(query)

    def focus_pane(self) -> None:
        self.query_one("#input", Input).focus()

    def on_show(self) -> None:
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
            self._submit(self.query_one("#input", Input).value)

    def _update_subagents(self) -> None:
        """Refresh the subagent activity banner (ticks twice a second).
        Appears whenever specialists are running, collapses when idle."""
        from tuney.agents import activity
        panel = self.query_one("#subagent-panel", Static)
        runs = activity.snapshot()
        was_hidden = panel.has_class("hidden")
        if not runs:
            if not was_hidden:
                panel.add_class("hidden")
                self.call_after_refresh(self._cap_reply)
            return
        lines = []
        for run in runs:
            task = " ".join(run["task"].split())
            if len(task) > 70:
                task = task[:69] + "…"
            lines.append(f"⚙ {run['agent']} · {run['elapsed']:.0f}s — {task}")
        panel.update("\n".join(lines))
        if was_hidden:
            panel.remove_class("hidden")
            self.call_after_refresh(self._cap_reply)

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

    def _start_stopwatch(self) -> int:
        self._stopwatch_gen += 1
        self._stopwatch_start = monotonic()
        if self._stopwatch_timer is not None:
            self._stopwatch_timer.stop()
        self._stopwatch_timer = self.set_interval(0.1, self._update_stopwatch)
        self.query_one("#stopwatch", Static).remove_class("hidden")
        self._update_stopwatch()
        # The stopwatch line takes a row from the pane, shrinking the dialog;
        # re-cap the reply.
        self.call_after_refresh(self._cap_reply)
        return self._stopwatch_gen

    def _update_stopwatch(self) -> None:
        elapsed = monotonic() - self._stopwatch_start
        try:
            self.query_one("#stopwatch", Static).update(f"⏱ {elapsed:.1f}s")
        except NoMatches:
            # Pane is being torn down; the widget is already gone.
            pass

    def _stop_stopwatch(self, gen: int) -> None:
        if gen != self._stopwatch_gen:
            return
        if self._stopwatch_timer is not None:
            self._stopwatch_timer.stop()
            self._stopwatch_timer = None
        # Freeze the final time on screen rather than hiding the line; the
        # next run resets and restarts it. (_update_stopwatch tolerates the
        # widget already being gone during worker teardown.)
        self._update_stopwatch()

    # ---- messaging --------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit(event.value)

    def _submit(self, value: str) -> None:
        text = value.strip()
        if not text:
            return
        self.query_one("#input", Input).value = ""
        # "Approve/reject all" only lasts for one agent run; each new request
        # starts with confirmations back on.
        self._approve_all = False
        self._reject_all = False
        self._set_focus_exchange(query=text, reply="Thinking...")
        self._append_history(text, "user")
        live = self._append_history("Thinking...", "ai")
        self._run_query(text, live)

    THINKING_TAIL_CHARS = 300

    async def _confirm(self, requests: list) -> list[dict]:
        """Show the confirmation dialog for each pending tool call, in order.

        Registered as the agents' confirmation handler, so specialists paused
        deep inside a supervisor delegation still reach the user's modal.
        The dialog shows the queue position when several calls are pending;
        "approve all" / "reject all" decide the rest of the current run.
        """
        reject = {"type": "reject", "message": "The user declined this action."}
        decisions = []
        for position, request in enumerate(requests, start=1):
            if self._approve_all:
                decisions.append({"type": "approve"})
                continue
            if self._reject_all:
                decisions.append(reject)
                continue
            result = await self.app.push_screen_wait(
                ConfirmModal(request, position=position, total=len(requests)))
            if result == "all":
                self._approve_all = True
                self.notify("Approving everything for the rest of this run.",
                            severity="warning")
            elif result == "reject_all":
                self._reject_all = True
                self.notify("Rejecting everything for the rest of this run.")
            decisions.append({"type": "approve"} if result == "all" or result is True
                             else reject)
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
                pending = await _render(tuney_agent.aresume(await self._confirm(pending)))
        except asyncio.CancelledError:
            # Worker cancelled (new query submitted, pane closed or rebuilt).
            # Keep any partial reply in its history bubble instead of losing
            # it silently; no awaits here — the task is already being torn
            # down, and Markdown.update runs without being awaited.
            partial = "".join(parts)
            interrupted = (f"{partial}\n\n*(interrupted)*" if partial
                           else "*(interrupted)*")
            hist_md.update(interrupted)
            self._record_exchange(text, live, interrupted)
            raise
        except Exception as e:
            from tuney.agents.Agent import error_detail
            self.log.error(f"agent stream failed: {e!r}")
            parts.append(f"\n\n**[error]** {error_detail(e)}")
            for s in await _streams():
                await s.write(parts[-1])
        finally:
            # Sync-only: on cancellation the task is already being torn down.
            self._stop_stopwatch(stopwatch)
            # The agent may have imported/retagged/deleted tracks; let the
            # workspace refresh the collection view and stats.
            self.post_message(self.AgentRunFinished())

        for s in streams:
            await s.stop()

        # stream finished — the AI is done responding
        if not parts:
            await reply.update("(no response)")
            await hist_md.update("(no response)")
        history.scroll_end(animate=False)
        self._record_exchange(text, live, "".join(parts) or "(no response)")

    def _record_exchange(self, query: str, live: Message, final: str) -> None:
        """Persist the finished reply to the transcript store so a rebuilt
        pane can replay it."""
        if live.state_index is not None:
            chat_state.update(live.state_index, final)
        chat_state.set_focus(query, final)

    def _set_focus_exchange(self, query: str, reply: str) -> None:
        """Replace the latest exchange shown in the focus view."""
        chat_state.set_focus(query, reply)
        self.query_one("#ai-reply", Markdown).update(reply)
        self.query_one("#user-query", Static).update(query)
        self.query_one("#ai-reply-scroll").scroll_home(animate=False)
        # The query height may have changed (wrapping); re-cap the reply panel.
        self.call_after_refresh(self._cap_reply)

    def _append_history(self, text: str, role: str) -> Message:
        """Append to the transcript store and the scrolling history view."""
        message = self._mount_history(text, role)
        message.state_index = chat_state.add(role, text)
        return message

    def _mount_history(self, text: str, role: str) -> Message:
        history = self.query_one("#history-scroll", VerticalScroll)
        message = Message(text, role)
        history.mount(message)
        history.scroll_end(animate=False)
        return message
