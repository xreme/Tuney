from textual.screen import Screen
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Input, Header, Footer, Static, Button
from tuney import config, credentials, library


class SettingScreen(Screen):
    """Configure Tuney: OpenRouter API key and chat model."""

    BINDINGS = [("escape", "back", "Back to menu")]

    DEFAULT_CSS = """
    SettingScreen VerticalScroll { padding: 1 2; }
    SettingScreen .section { text-style: bold; margin-top: 1; }
    SettingScreen .hint { color: $text-muted; }
    SettingScreen Input { max-width: 70; margin-top: 1; }
    SettingScreen Horizontal { height: auto; margin-top: 1; }
    SettingScreen Button { margin-right: 2; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("OpenRouter API key", classes="section")
            yield Static(id="key-status", classes="hint")
            yield Input(placeholder="sk-or-...", password=True, id="key-input")
            with Horizontal():
                yield Button("Save to keychain", id="key-save", variant="primary")
                yield Button("Remove from keychain", id="key-remove", variant="error")

            yield Static("Chat model", classes="section")
            yield Static(
                "Any OpenRouter model id. Takes effect the next time the "
                "chat agent starts (restart Tuney if you've already chatted).",
                classes="hint",
            )
            yield Input(placeholder=config.DEFAULT_CHAT_MODEL, id="model-input")
            with Horizontal():
                yield Button("Save model", id="model-save", variant="primary")
                yield Button("Reset to default", id="model-reset")

            yield Static("About", classes="section")
            yield Static(id="about", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#model-input", Input).value = config.get_config().chat_model
        self._refresh_key_status()
        self.query_one("#about", Static).update(
            f"Library database: {library.DB}\n"
            f"Settings file:    {config.config_file}\n"
            f"Tracks indexed:   {len(library.all_items())}"
        )

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

    def action_back(self) -> None:
        self.app.pop_screen()
