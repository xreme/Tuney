from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Button, Input, Label, RadioButton, RadioSet, RichLog, Select, Static)
from rich.text import Text

from tuney import config, library


def format_size(num_bytes: int) -> str:
    if num_bytes >= 1_073_741_824:
        return f"{num_bytes / 1_073_741_824:.1f} GB"
    return f"{num_bytes / 1_048_576:.0f} MB"


class ConvertModal(ModalScreen):
    CSS = """
    ConvertModal { align: center middle; }
    #convert-dialog {
        width: 80%;
        max-width: 90;
        height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #convert-form { height: 1fr; }
    ConvertModal .field-label { text-style: bold; margin-top: 1; }
    ConvertModal .hint { color: $text-muted; }
    #convert-plan {
        margin-top: 1;
        padding: 1;
        border: round $panel;
        height: auto;
    }
    #convert-buttons { height: auto; margin-top: 1; align-horizontal: center; }
    #convert-buttons Button { margin: 0 1; }
    #convert-log { height: 1fr; }
    .hidden { display: none; }
    """

    BINDINGS = [("escape", "back", "Close")]

    # Recompute the plan only once typing pauses; each pass reads the library.
    PLAN_DEBOUNCE = 0.3

    def __init__(self, query: str = "", album: bool = False,
                 scope_label: str | None = None) -> None:
        """`scope_label` replaces the query box for a set the user already
        marked, whose query is a hundred ORed ids nobody can edit."""
        super().__init__()
        self._convert_query = query
        self._album_mode = album
        self._scope_label = scope_label
        self._plan_timer = None
        self._converting = False

    def compose(self) -> ComposeResult:
        cfg = config.get_config()
        with Container(id="convert-dialog"):
            yield Label("Convert music", id="modal-title")
            with VerticalScroll(id="convert-form"):
                yield Static("Tracks to convert", classes="field-label")
                if self._scope_label is not None:
                    yield Static(self._scope_label, id="convert-scope")
                else:
                    yield Static("A beets query, the same as the search box. "
                                 "Leave it empty to convert your whole library.",
                                 classes="hint")
                    yield Input(value=self._convert_query,
                                placeholder="artist:radiohead year:2000..",
                                id="convert-query")

                yield Static("Format", classes="field-label")
                yield Select([(fmt.upper(), fmt) for fmt in library.CONVERT_FORMATS],
                             value=str(cfg.convert_format), allow_blank=False,
                             id="convert-format")

                yield Static("Quality", classes="field-label")
                with RadioSet(id="convert-quality"):
                    yield RadioButton("Normal", id="q-normal",
                                      value=cfg.convert_quality
                                      is config.ConvertQuality.NORMAL)
                    yield RadioButton("Best", id="q-best",
                                      value=cfg.convert_quality
                                      is config.ConvertQuality.BEST)
                yield Static(id="convert-quality-note", classes="hint")

                yield Static("Mode", classes="field-label")
                with RadioSet(id="convert-mode"):
                    yield RadioButton(
                        "Export — write converted copies, leave my library alone",
                        value=True, id="mode-export")
                    yield RadioButton(
                        "Replace — point my library at the converted files",
                        id="mode-replace")

                yield Static("Destination", classes="field-label")
                yield Static(id="convert-dest-hint", classes="hint")
                yield Input(value=cfg.convert_dest_path, id="convert-dest")

                yield Static("Reading your library…", id="convert-plan")
            with Horizontal(id="convert-buttons"):
                yield Button("Convert", id="convert-start", variant="primary")
                yield Button("Cancel", id="convert-cancel")
            yield RichLog(id="convert-log", wrap=True, classes="hidden")
            yield Label(r"\[esc] close", id="modal-hint")

    def on_mount(self) -> None:
        self._refresh_dest_hint()
        self._refresh_quality()
        self._recompute_plan()
        if self._scope_label is None:
            self.query_one("#convert-query", Input).focus()
        else:
            self.query_one("#convert-format", Select).focus()

    # ---- form state --------------------------------------------------------

    def _current_query(self) -> str:
        if self._scope_label is not None:
            return self._convert_query
        return self.query_one("#convert-query", Input).value.strip()

    def _replacing(self) -> bool:
        return self.query_one("#mode-replace", RadioButton).value

    def _format(self) -> str:
        value = self.query_one("#convert-format", Select).value
        return str(value) if value is not Select.BLANK else str(config.ConvertFormat.MP3)

    def _quality(self) -> str:
        return str(config.ConvertQuality.BEST
                   if self.query_one("#q-best", RadioButton).value
                   else config.ConvertQuality.NORMAL)

    def _remember_quality(self, fmt: str, quality: str) -> None:
        """Saved on start rather than on the radio change: a tier clicked
        through while comparing the notes isn't a preference, one they
        converted at is. Skipped where the control is disabled (ALAC)."""
        if not library.quality_is_meaningful(fmt):
            return
        cfg = config.get_config()
        tier = config.ConvertQuality(quality)
        if cfg.convert_quality is tier:
            return
        cfg.convert_quality = tier
        cfg.save()

    def _refresh_quality(self) -> None:
        fmt = self._format()
        meaningful = library.quality_is_meaningful(fmt)
        for tier in (config.ConvertQuality.NORMAL, config.ConvertQuality.BEST):
            button = self.query_one(f"#q-{tier}", RadioButton)
            button.label = (
                f"{str(tier).capitalize()} — {library.quality_summary(fmt, tier)}"
                if meaningful else str(tier).capitalize())
        self.query_one("#convert-quality", RadioSet).disabled = not meaningful
        note = self.query_one("#convert-quality-note", Static)
        if not meaningful:
            note.update(f"{fmt.upper()} is lossless with no quality setting — "
                        "the audio is an exact copy either way.")
        elif library.is_lossless(fmt):
            note.update("Lossless: both options give you the exact same audio. "
                        "Best only compresses harder, for a smaller file and a "
                        "slower conversion.")
        else:
            note.update("Higher quality means bigger files. Converting a lossy "
                        "file can never recover quality it already lost.")

    def _refresh_dest_hint(self) -> None:
        replacing = self._replacing()
        self.query_one("#convert-dest-hint", Static).update(
            "Where your ORIGINAL files are moved. They are never deleted, so "
            "a conversion you regret can be undone from here."
            if replacing else
            "Where the converted copies are written.")

    @on(Input.Changed, "#convert-query")
    def _on_query_changed(self, _event: Input.Changed) -> None:
        if self._plan_timer is not None:
            self._plan_timer.stop()
        self._plan_timer = self.set_timer(self.PLAN_DEBOUNCE, self._recompute_plan)

    @on(Select.Changed, "#convert-format")
    def _on_format_changed(self, _event: Select.Changed) -> None:
        self._refresh_quality()
        self._recompute_plan()

    @on(RadioSet.Changed, "#convert-quality")
    def _on_quality_changed(self, _event: RadioSet.Changed) -> None:
        self._refresh_quality()

    @on(RadioSet.Changed, "#convert-mode")
    def _on_mode_changed(self, _event: RadioSet.Changed) -> None:
        self._refresh_dest_hint()
        cfg = config.get_config()
        # Swap the destination only while it still holds the other mode's
        # default — a path the user typed themselves is theirs to keep.
        dest = self.query_one("#convert-dest", Input)
        defaults = {cfg.convert_dest_path, cfg.convert_archive_path}
        if dest.value.strip() in defaults:
            dest.value = (cfg.convert_archive_path if self._replacing()
                          else cfg.convert_dest_path)
        self._recompute_plan()

    # ---- plan --------------------------------------------------------------

    def _recompute_plan(self) -> None:
        if self._converting:
            return
        self._load_plan(self._current_query(), self._format(), self._replacing())

    @work(thread=True, exclusive=True)
    def _load_plan(self, query: str, fmt: str, replacing: bool) -> None:
        """A whole-library read; far too slow for the event loop."""
        try:
            plan = library.convert_plan(query, fmt, album=self._album_mode)
        except Exception as error:
            text = Text(f"Couldn't read the library: {error}", style="red")
        else:
            text = self._plan_text(plan, fmt, replacing)
        self.app.call_from_thread(self._show_plan, text)

    def _plan_text(self, plan: dict, fmt: str, replacing: bool) -> Text:
        text = Text()
        if not plan["matched"]:
            return Text("Nothing matches that query.", style="yellow")

        if self._scope_label is not None:
            unit = "track" if plan["matched"] == 1 else "tracks"
            text.append(f"{plan['matched']} {unit} selected.\n")
        else:
            scope = ("your ENTIRE library" if plan["whole_library"]
                     else "this query")
            text.append(f"{plan['matched']} tracks match {scope}.\n")
        text.append(f"  {plan['transcode']} to convert to {fmt.upper()}",
                    style="bold")
        text.append(f" ({format_size(plan['source_bytes'])} of source audio)\n")
        if plan["skipped"]:
            text.append(f"  {plan['skipped']} already {fmt.upper()} — copied, "
                        "not re-encoded\n")
        if plan["unreachable"]:
            reasons = ", ".join(f"{count} {reason}" for reason, count
                                in plan["unreachable_by_reason"].items())
            text.append(f"  {plan['unreachable']} unreachable ({reasons}) — "
                        "skipped\n", style="yellow")
        if plan["lossy_reencode"]:
            text.append(f"  {plan['lossy_reencode']} are lossy → lossy "
                        "re-encodes and will lose quality\n", style="yellow")
        if replacing:
            text.append("\nYour library will point at the new files. The "
                        "originals are MOVED to the destination — nothing is "
                        "deleted.", style="yellow")
        return text

    def _show_plan(self, text: Text) -> None:
        try:
            self.query_one("#convert-plan", Static).update(text)
        except NoMatches:
            pass      # dialog closed while the library was being read

    # ---- run ---------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "convert-cancel":
            self.action_back()
        elif event.button.id == "convert-start":
            self._start()

    def _start(self) -> None:
        if self._converting:
            return
        dest = self.query_one("#convert-dest", Input).value.strip()
        if not dest:
            self.notify("Choose a destination folder first.", severity="warning")
            return
        self._converting = True
        query = self._current_query()
        fmt, replacing, quality = self._format(), self._replacing(), self._quality()
        self._remember_quality(fmt, quality)

        self.query_one("#convert-form").display = False
        self.query_one("#convert-buttons").display = False
        self.query_one("#convert-log").remove_class("hidden")
        title = f"Converting to {fmt.upper()}…"
        if library.quality_is_meaningful(fmt):
            title = f"Converting to {fmt.upper()} ({quality})…"
        self.query_one("#modal-title", Label).update(title)
        self.run_worker(
            lambda: self._run(query, fmt, dest, replacing, quality), thread=True)

    def _run(self, query: str, fmt: str, dest: str, replacing: bool,
             quality: str) -> None:
        log = self.query_one("#convert-log", RichLog)
        lines = []
        try:
            for line in library.convert_stream(query, fmt, dest,
                                               replace=replacing,
                                               album=self._album_mode,
                                               quality=quality):
                lines.append(line)
                self.app.call_from_thread(log.write, line)
        except Exception as error:
            self.app.call_from_thread(
                log.write, Text(f"Conversion failed: {error}", style="red"))
        self.app.call_from_thread(self._show_verdict, "\n".join(lines), dest)

    def _show_verdict(self, log: str, dest: str) -> None:
        # beets skips files whose target exists and reports failed encodes per
        # file while still exiting 0, so "Done" alone can be a lie.
        done = library.convert_outcome(log)
        widget = self.query_one("#convert-log", RichLog)
        if done["wrote"]:
            verdict = Text(f"Done — {done['wrote']} file(s) written to {dest}.",
                           style="bold green")
        elif done["existing"]:
            verdict = Text(
                f"Nothing written. All {done['existing']} file(s) are already "
                f"in {dest} — beets never overwrites, so delete or move them "
                "there to convert again.", style="bold yellow")
        elif done["failed"] or done["unreadable"]:
            verdict = Text(
                f"FAILED — nothing was written to {dest}. The encoder errored; "
                "the log above says why. Your files are unchanged.",
                style="bold red")
        else:
            verdict = Text(f"Nothing was written to {dest}.",
                           style="bold yellow")
        widget.write(verdict)
        widget.write(Text.from_markup(r"[dim]Press \[ESC] to close.[/dim]"))

    def action_back(self) -> None:
        self.app.pop_screen()
