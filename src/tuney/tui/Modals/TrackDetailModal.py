import io
import os

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from tuney import library


# Art rendered as half-block "pixels": one character cell shows two vertical
# pixels (▀ foreground on background), so a width×height cell canvas holds a
# width×(height*2) pixel image.
ART_CELL_WIDTH = 26
ART_CELL_HEIGHT = 13


def render_art(data: bytes, cell_width: int = ART_CELL_WIDTH,
               cell_height: int = ART_CELL_HEIGHT) -> Text:
    """Decode image bytes and paint them with half-block characters."""
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    # Ask the JPEG decoder for a reduced-scale decode up front — far cheaper
    # than decoding a full-size cover and then shrinking it.
    image.draft("RGB", (cell_width * 8, cell_height * 16))
    image = image.convert("RGB")
    image.thumbnail((cell_width, cell_height * 2))
    pixels = image.load()
    text = Text()
    for y in range(0, image.height - image.height % 2, 2):
        for x in range(image.width):
            top = "#{:02x}{:02x}{:02x}".format(*pixels[x, y])
            bottom = "#{:02x}{:02x}{:02x}".format(*pixels[x, y + 1])
            text.append("▀", style=f"{top} on {bottom}")
        text.append("\n")
    return text


def load_art_bytes(item) -> bytes | None:
    """The track's cover art: the beets album art file if there is one,
    otherwise art embedded in the audio file itself. None when neither is
    reachable (e.g. the drive isn't mounted)."""
    try:
        album = library.get_album(item.album_id) if item.album_id else None
        if album is not None and album.artpath:
            path = os.fsdecode(album.artpath)
            if os.path.exists(path):
                with open(path, "rb") as file:
                    return file.read()
    except Exception:
        pass
    try:
        from mediafile import MediaFile
        images = MediaFile(os.fsdecode(item.path)).images
        if images:
            return images[0].data
    except Exception:
        pass
    return None


class TrackDetailModal(ModalScreen):
    """Cover art and full metadata for one collection track."""

    CSS = """
    TrackDetailModal { align: center middle; }
    #detail-dialog {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 80%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #detail-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #detail-body { height: auto; }
    #detail-art {
        width: 28;
        height: auto;
        margin-right: 2;
        color: $text-muted;
    }
    #detail-fields-scroll {
        width: 1fr;
        height: auto;
        max-height: 26;
    }
    #detail-fields { width: 1fr; height: auto; }
    #detail-hint { width: 100%; text-align: center; padding-top: 1; }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
        ("enter", "close", "Close"),
    ]

    def __init__(self, item) -> None:
        super().__init__()
        self._item = item

    def compose(self) -> ComposeResult:
        item = self._item
        title = str(item.title or "") or os.path.basename(os.fsdecode(item.path))
        with Container(id="detail-dialog"):
            yield Label(title, id="detail-title")
            with Horizontal(id="detail-body"):
                yield Static("Loading art…", id="detail-art")
                with VerticalScroll(id="detail-fields-scroll", can_focus=False):
                    yield Static(self._fields_text(), id="detail-fields")
            yield Label(r"\[esc]/\[enter] close | \[↑↓] scroll", id="detail-hint")

    def on_mount(self) -> None:
        self._load_art()

    # Rendered art per file path, so reopening a track skips the file read
    # and decode entirely.
    _art_cache: dict[bytes, Text] = {}
    _ART_CACHE_MAX = 64

    @work(thread=True)
    def _load_art(self) -> None:
        """Read and decode the art off the event loop — the file may live on
        a slow (or unmounted) external drive."""
        key = self._item.path or b""
        art = self._art_cache.get(key)
        if art is None:
            data = load_art_bytes(self._item)
            try:
                art = render_art(data) if data else Text("No artwork found")
            except Exception:
                art = Text("No artwork found")
            if len(self._art_cache) >= self._ART_CACHE_MAX:
                self._art_cache.pop(next(iter(self._art_cache)))
            self._art_cache[key] = art
        self.app.call_from_thread(
            self.query_one("#detail-art", Static).update, art)

    def _fields_text(self) -> Text:
        item = self._item

        def fmt_length(seconds):
            minutes, secs = divmod(int(seconds or 0), 60)
            return f"{minutes}:{secs:02d}"

        genres = getattr(item, "genres", None) or []
        rows = [
            ("Artist", item.artist or "Unknown"),
            ("Album", item.album or "Unknown"),
            ("Album artist", item.albumartist or ""),
            ("Year", item.year or ""),
            ("Genre", ", ".join(genres)),
            ("Track", f"{item.track}/{item.tracktotal}"
                      if getattr(item, "track", 0) else ""),
            ("Length", fmt_length(item.length)),
            ("Format", item.format or ""),
            ("Bitrate", f"{item.bitrate // 1000} kbps"
                        if getattr(item, "bitrate", 0) else ""),
            ("Sample rate", f"{item.samplerate / 1000:g} kHz"
                            if getattr(item, "samplerate", 0) else ""),
            ("File", os.fsdecode(item.path) if item.path else ""),
        ]
        text = Text()
        for label, value in rows:
            if value == "" or value is None:
                continue
            text.append(f"{label:>13}  ", style="bold")
            text.append(f"{value}\n")
        return text

    def action_close(self) -> None:
        self.dismiss()
