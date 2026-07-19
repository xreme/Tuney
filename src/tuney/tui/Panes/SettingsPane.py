from textual import on, work
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Static, Button, RadioButton, RadioSet
from tuney import config, credentials, library
from .base import Pane


class SettingsPane(Pane):
    """Configure Tuney: auto-tagging, OpenRouter API key and chat model."""

    PANE_NAME = "Settings"

    DEFAULT_CSS = """
    SettingsPane VerticalScroll { padding: 1 2; }
    SettingsPane .section { text-style: bold; margin-top: 1; }
    SettingsPane .hint { color: $text-muted; }
    SettingsPane Input { max-width: 70; margin-top: 1; }
    SettingsPane Horizontal { height: auto; margin-top: 1; }
    SettingsPane Button { margin-right: 2; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Auto-tagging", classes="section")
            yield Static("Configure the behaviour of tagging when songs are imported")
            with RadioSet(id="Autotag-set"):
                yield RadioButton("Off — import files as-is, no metadata lookup", id="autotag-off")
                yield RadioButton("Safe — fix metadata, skip albums without a confident match", id="autotag-safe")
                yield RadioButton("Keep — fix metadata, import uncertain albums with their existing tags", id="autotag-keep")

            yield Static("OpenRouter API key", classes="section")
            yield Static(id="key-status", classes="hint")
            yield Input(placeholder="sk-or-...", password=True, id="key-input")
            with Horizontal():
                yield Button("Save to keychain", id="key-save", variant="primary")
                yield Button("Remove from keychain", id="key-remove", variant="error")

            yield Static("Chat model", classes="section")
            yield Static(
                "Any OpenRouter model id. Takes effect on your next message.",
                classes="hint",
            )
            yield Input(placeholder=config.DEFAULT_CHAT_MODEL, id="model-input")
            with Horizontal():
                yield Button("Save model", id="model-save", variant="primary")
                yield Button("Reset to default", id="model-reset")

            yield Static("Chat detail", classes="section")
            yield Static(
                "How much information Tuney packs into replies. Also "
                "switchable from the chat pane (^d). Takes effect on your "
                "next message.",
                classes="hint",
            )
            with RadioSet(id="detail-set"):
                yield RadioButton("Low — essentials only", id="detail-low")
                yield RadioButton("Normal — essentials plus a little extra", id="detail-normal")
                yield RadioButton("High — lots of information, more verbose", id="detail-high")

            yield Static("About", classes="section")
            yield Static(id="about", classes="hint")

    def on_mount(self) -> None:
        cfg = config.get_config()
        self.query_one("#model-input", Input).value = cfg.chat_model
        self.query_one(f"#detail-{cfg.chat_detail}", RadioButton).value = True
        self.query_one(f"#autotag-{cfg.import_autotag}", RadioButton).value = True
        self._refresh_key_status()
        self.query_one("#about", Static).update(
            f"Library database: {library.DB}\n"
            f"Settings file:    {config.config_file}\n"
            f"Tracks indexed:   counting…"
        )
        self._load_track_count()

    @work(thread=True)
    def _load_track_count(self) -> None:
        count = len(library.all_items())

        def show() -> None:
            try:
                about = self.query_one("#about", Static)
            except NoMatches:
                return      # pane closed while the library was being counted
            about.update(
                f"Library database: {library.DB}\n"
                f"Settings file:    {config.config_file}\n"
                f"Tracks indexed:   {count}",
            )

        self.app.call_from_thread(show)

    def _refresh_key_status(self) -> None:
        env_key = credentials.env_api_key()
        stored = credentials.keychain_api_key()
        if env_key:
            status = (
                "Using the key from the OPENROUTER_API_KEY environment "
                "variable (e.g. .env); it overrides the keychain entry."
            )
            if stored:
                status += f"\nA key is also saved in the keychain (…{stored[-4:]})."
        elif stored:
            status = f"Using the key saved in the system keychain (…{stored[-4:]})."
        else:
            status = "No key configured — the chat assistant won't work without one."
        self.query_one("#key-status", Static).update(status)

    # ---- actions -----------------------------------------------------------

    @on(RadioSet.Changed, "#Autotag-set")
    def on_autotag_changed(self, event: RadioSet.Changed) -> None:
        mode = config.ImportAutotagMode(event.pressed.id.removeprefix("autotag-"))
        cfg = config.get_config()
        if cfg.import_autotag == mode:   # on_mount preselection, not a change
            return
        cfg.import_autotag = mode
        cfg.save()
        self.notify(f"Import auto-tagging set to {mode}.")

    @on(RadioSet.Changed, "#detail-set")
    def on_detail_changed(self, event: RadioSet.Changed) -> None:
        detail = config.ChatDetail(event.pressed.id.removeprefix("detail-"))
        cfg = config.get_config()
        if cfg.chat_detail == detail:    # on_mount preselection, not a change
            return
        cfg.chat_detail = detail
        cfg.save()
        self.notify(f"Chat detail set to {detail}.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "key-save":
            self._save_key()
        elif event.button.id == "key-remove":
            self._remove_key()
        elif event.button.id == "model-save":
            self._save_model(self.query_one("#model-input", Input).value)
        elif event.button.id == "model-reset":
            self.query_one("#model-input", Input).value = config.DEFAULT_CHAT_MODEL
            self._save_model(config.DEFAULT_CHAT_MODEL)

    def _save_key(self) -> None:
        key_input = self.query_one("#key-input", Input)
        value = key_input.value.strip()
        if not value:
            self.notify("Enter a key first.", severity="warning")
            return
        credentials.save_api_key(value)
        key_input.value = ""
        self._refresh_key_status()
        if credentials.env_api_key():
            self.notify(
                "Saved, but OPENROUTER_API_KEY is set in the environment "
                "and takes precedence.",
                severity="warning",
            )
        else:
            self.notify("API key saved to the keychain.")

    def _remove_key(self) -> None:
        if credentials.delete_api_key():
            self.notify("API key removed from the keychain.")
        else:
            self.notify("No key stored in the keychain.", severity="warning")
        self._refresh_key_status()

    def _save_model(self, value: str) -> None:
        value = value.strip()
        if not value:
            self.notify("Enter a model id first.", severity="warning")
            return
        cfg = config.get_config()
        cfg.chat_model = value
        cfg.save()
        self.notify(f"Chat model set to {value}.")
