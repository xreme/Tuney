import os

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

            yield Static("Conversion", classes="section")
            yield Static(
                "Defaults for converting audio files. Every conversion still "
                "asks before it runs.",
                classes="hint",
            )
            with RadioSet(id="convert-format-set"):
                yield RadioButton("MP3 — lossy, plays anywhere", id="cfmt-mp3")
                yield RadioButton("AAC — lossy, Apple devices (.m4a)", id="cfmt-aac")
                yield RadioButton("Opus — lossy, best quality per byte", id="cfmt-opus")
                yield RadioButton("Ogg — lossy, Vorbis", id="cfmt-ogg")
                yield RadioButton("ALAC — lossless, Apple devices (.m4a)", id="cfmt-alac")
                yield RadioButton("FLAC — lossless", id="cfmt-flac")

            yield Static(
                "Default quality. For MP3/AAC/Opus/Ogg, Best raises the "
                "bitrate; FLAC and ALAC are lossless, so Best only compresses "
                "harder — the audio is identical either way.",
                classes="hint",
            )
            with RadioSet(id="convert-quality-set"):
                yield RadioButton("Normal — smaller files, still good quality",
                                  id="cq-normal")
                yield RadioButton("Best — maximum quality", id="cq-best")

            yield Static("Where converted copies are written.", classes="hint")
            yield Input(placeholder=config.default_convert_dest(),
                        id="convert-dest-input")
            yield Static(
                "Where originals are moved when a conversion replaces them in "
                "your library. They are never deleted, so a conversion you "
                "regret can be undone from here.",
                classes="hint",
            )
            yield Input(placeholder=config.default_convert_archive(),
                        id="convert-archive-input")
            with Horizontal():
                yield Button("Save folders", id="convert-paths-save",
                             variant="primary")
                yield Button("Reset to defaults", id="convert-paths-reset")

            yield Static("OpenRouter API key", classes="section")
            yield Static(id="key-status", classes="hint")
            yield Input(placeholder="sk-or-...", password=True, id="key-input")
            with Horizontal():
                yield Button("Save to keychain", id="key-save", variant="primary")
                yield Button("Remove from keychain", id="key-remove", variant="error")

            yield Static("Last.fm API key", classes="section")
            yield Static(
                "Optional. Adds Last.fm alongside MusicBrainz when searching "
                "for music to wishlist, and as a cover-art source. Get one at "
                "https://www.last.fm/api/account/create",
                classes="hint",
            )
            yield Static(id="lastfm-status", classes="hint")
            yield Input(placeholder="Last.fm API key", password=True,
                        id="lastfm-input")
            with Horizontal():
                yield Button("Save to keychain", id="lastfm-save", variant="primary")
                yield Button("Remove from keychain", id="lastfm-remove", variant="error")

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
        self._sync_convert_defaults()
        self.query_one("#convert-dest-input", Input).value = cfg.convert_dest
        self.query_one("#convert-archive-input", Input).value = cfg.convert_archive
        self._refresh_key_status()
        self._refresh_lastfm_status()
        self.query_one("#about", Static).update(
            f"Library database: {library.DB}\n"
            f"Settings file:    {config.config_file}\n"
            f"Tracks indexed:   counting…"
        )
        self._load_track_count()

    def on_show(self) -> None:
        # The convert dialog writes the tier it ran at back to the config, so
        # these can go stale while the pane sits in another tab.
        self._sync_convert_defaults()

    def _sync_convert_defaults(self) -> None:
        cfg = config.get_config()
        self.query_one(f"#cfmt-{cfg.convert_format}", RadioButton).value = True
        self.query_one(f"#cq-{cfg.convert_quality}", RadioButton).value = True

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

    def _refresh_lastfm_status(self) -> None:
        env_key = credentials.env_lastfm_key()
        stored = credentials.keychain_lastfm_key()
        if env_key:
            status = ("Using the key from the LASTFM_API_KEY environment "
                      "variable; it overrides the keychain entry.")
            if stored:
                status += f"\nA key is also saved in the keychain (…{stored[-4:]})."
        elif stored:
            status = f"Using the key saved in the system keychain (…{stored[-4:]})."
        else:
            status = ("No key configured — searches use MusicBrainz only.")
        self.query_one("#lastfm-status", Static).update(status)

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

    @on(RadioSet.Changed, "#convert-format-set")
    def on_convert_format_changed(self, event: RadioSet.Changed) -> None:
        fmt = config.ConvertFormat(event.pressed.id.removeprefix("cfmt-"))
        cfg = config.get_config()
        if cfg.convert_format == fmt:     # on_mount preselection, not a change
            return
        cfg.convert_format = fmt
        cfg.save()
        self.notify(f"Conversion format set to {fmt}.")

    @on(RadioSet.Changed, "#convert-quality-set")
    def on_convert_quality_changed(self, event: RadioSet.Changed) -> None:
        tier = config.ConvertQuality(event.pressed.id.removeprefix("cq-"))
        cfg = config.get_config()
        if cfg.convert_quality == tier:   # on_mount preselection, not a change
            return
        cfg.convert_quality = tier
        cfg.save()
        self.notify(f"Conversion quality set to {tier}.")

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
        elif event.button.id == "lastfm-save":
            self._save_lastfm_key()
        elif event.button.id == "lastfm-remove":
            self._remove_lastfm_key()
        elif event.button.id == "model-save":
            self._save_model(self.query_one("#model-input", Input).value)
        elif event.button.id == "model-reset":
            self.query_one("#model-input", Input).value = config.DEFAULT_CHAT_MODEL
            self._save_model(config.DEFAULT_CHAT_MODEL)
        elif event.button.id == "convert-paths-save":
            self._save_convert_paths()
        elif event.button.id == "convert-paths-reset":
            self.query_one("#convert-dest-input", Input).value = ""
            self.query_one("#convert-archive-input", Input).value = ""
            self._save_convert_paths()

    def _save_convert_paths(self) -> None:
        dest = self.query_one("#convert-dest-input", Input).value.strip()
        archive = self.query_one("#convert-archive-input", Input).value.strip()
        cfg = config.get_config()
        # One folder for both would let a replace drop originals on top of
        # exported copies.
        if dest and archive and os.path.abspath(dest) == os.path.abspath(archive):
            self.notify("The converted-copies folder and the originals archive "
                        "must be different.", severity="error")
            return
        cfg.convert_dest = dest
        cfg.convert_archive = archive
        cfg.save()
        self.notify("Conversion folders saved.")

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

    def _save_lastfm_key(self) -> None:
        key_input = self.query_one("#lastfm-input", Input)
        value = key_input.value.strip()
        if not value:
            self.notify("Enter a key first.", severity="warning")
            return
        credentials.save_lastfm_key(value)
        key_input.value = ""
        self._refresh_lastfm_status()
        if credentials.env_lastfm_key():
            self.notify(
                "Saved, but LASTFM_API_KEY is set in the environment and "
                "takes precedence.",
                severity="warning",
            )
        else:
            self.notify("Last.fm API key saved to the keychain.")

    def _remove_lastfm_key(self) -> None:
        if credentials.delete_lastfm_key():
            self.notify("Last.fm API key removed from the keychain.")
        else:
            self.notify("No Last.fm key stored in the keychain.",
                        severity="warning")
        self._refresh_lastfm_status()

    def _save_model(self, value: str) -> None:
        value = value.strip()
        if not value:
            self.notify("Enter a model id first.", severity="warning")
            return
        cfg = config.get_config()
        cfg.chat_model = value
        cfg.save()
        self.notify(f"Chat model set to {value}.")
