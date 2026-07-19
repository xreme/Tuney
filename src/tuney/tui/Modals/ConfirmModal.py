import os

from textual import work
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.widgets import Button, Label, Static
from textual.containers import Container, Horizontal, VerticalScroll
from rich.text import Text

from tuney import library


class ConfirmModal(ModalScreen[bool | str]):
    """Approve/reject dialog for a tool call paused by the HITL middleware.

    Dismisses with True (approve), False (reject), "all" (approve this and
    every further request in the current agent run) or "reject_all" (reject
    this and every further request in the run). Escape rejects, so an
    abandoned dialog never silently approves a destructive action.

    `position`/`total` describe the pending queue ("2 of 5") when the agent
    paused on several tool calls at once.
    """

    CSS = """
    ConfirmModal { align: center middle; }
    #confirm-dialog {
        width: 80%;
        max-width: 80;
        height: auto;
        border: solid $warning;
        background: $surface;
        padding: 1 2;
    }
    #modal-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #confirm-detail-scroll {
        width: 100%;
        height: auto;
        max-height: 60vh;
        margin-bottom: 1;
    }
    #confirm-detail {
        width: 100%;
        height: auto;
    }
    #confirm-buttons {
        width: 100%;
        height: auto;
        align-horizontal: center;
    }
    /* Four buttons share one row — let them shrink to their labels. */
    #confirm-buttons Button { margin: 0 1; min-width: 0; width: auto; }
    """

    BINDINGS = [
        ("escape", "reject", "Reject"),
        ("y", "approve", "Approve"),
        ("a", "approve_all", "Approve all"),
        ("n", "reject", "Reject"),
        ("r", "reject_all", "Reject all"),
        ("up", "scroll_detail(-1)", "Scroll up"),
        ("down", "scroll_detail(1)", "Scroll down"),
        ("pageup", "scroll_detail_page(-1)", "Page up"),
        ("pagedown", "scroll_detail_page(1)", "Page down"),
    ]

    def __init__(self, request: dict, position: int = 1, total: int = 1) -> None:
        super().__init__()
        self._request = request
        self._position = position
        self._total = total

    TITLE_STYLE = "bold cyan"
    ALBUM_STYLE = "italic magenta"
    PATH_STYLE = "yellow"

    def _describe(self) -> Text | None:
        """Human-friendly text for known tools; None falls back to the raw view."""
        name = self._request.get("name")
        args = self._request.get("args", {})
        if name == "remove_item":
            return self._describe_item(args.get("item_id"), bool(args.get("delete_file")))
        if name == "remove_items":
            return self._describe_batch(list(args.get("item_ids") or []),
                                        bool(args.get("delete_files")))
        if name == "remove_album":
            return self._describe_album(args.get("album_id"), bool(args.get("delete_files")))
        if name == "retag_collection":
            return self._describe_retag(str(args.get("query") or ""))
        if name == "set_track_tags":
            return self._describe_set_tags(args.get("item_id"), args)
        if name == "apply_track_tags":
            return self._describe_apply_tags(
                args.get("item_id"),
                str(args.get("artist") or "?"),
                str(args.get("title") or "?"),
                note="Fetching the full list of changes from MusicBrainz…")
        return None

    @staticmethod
    def _lookup_item(item_id):
        try:
            return library.get_item(item_id)
        except Exception:
            return None

    def _item_fields(self, item_id) -> tuple[str, str | None, str | None, str | None]:
        """(title, artist, album, path) for an id, with fallbacks for bad ids."""
        item = self._lookup_item(item_id)
        if item is None:
            return f"item {item_id}", None, None, None
        fields = dict(item)
        return (
            str(fields.get("title") or f"item {item_id}"),
            str(fields.get("artist") or "") or None,
            str(fields.get("album") or "") or None,
            os.fsdecode(item.path) if item.path else None,
        )

    def _describe_item(self, item_id, delete: bool) -> Text:
        title, artist, album, path = self._item_fields(item_id)
        text = Text()
        text.append("Tuney would like to permanently delete " if delete
                    else "Tuney would like to remove ")
        text.append(title, style=self.TITLE_STYLE)
        if artist:
            text.append(f" by {artist}")
        if album:
            text.append(" from the album ")
            text.append(album, style=self.ALBUM_STYLE)
        if delete:
            text.append(".\n\n")
            if path:
                text.append("File: ")
                text.append(path, style=self.PATH_STYLE)
                text.append("\n\n")
            text.append("The audio file will be deleted from disk — this cannot be undone.")
        else:
            text.append(" from your library.\n\nThe audio file will stay on disk.")
        return text

    def _describe_batch(self, item_ids: list, delete: bool) -> Text:
        count = len(item_ids)
        tracks_word = "track" if count == 1 else "tracks"
        text = Text()
        text.append(f"Tuney would like to permanently delete these {count} {tracks_word}:\n\n"
                    if delete else
                    f"Tuney would like to remove these {count} {tracks_word} from your library:\n\n")
        for item_id in item_ids:
            title, artist, _album, path = self._item_fields(item_id)
            text.append("  • ")
            text.append(title, style=self.TITLE_STYLE)
            if artist:
                text.append(f" by {artist}")
            if delete and path:
                text.append("\n    ")
                text.append(path, style=self.PATH_STYLE)
            text.append("\n")
        text.append("\nThe audio files will be deleted from disk — this cannot be undone."
                    if delete else
                    "\nThe audio files will stay on disk.")
        return text

    def _describe_album(self, album_id, delete: bool) -> Text:
        try:
            album = library.get_album(album_id)
        except Exception:
            album = None
        name = f"album {album_id}"
        artist = None
        tracks: list | None = None
        if album is not None:
            name = str(album.album or name)
            artist = str(album.albumartist or "") or None
            tracks = list(album.items())
        text = Text()
        text.append("Tuney would like to permanently delete the album "
                    if delete else "Tuney would like to remove the album ")
        text.append(name, style=self.ALBUM_STYLE)
        if artist:
            text.append(f" by {artist}")
        if not delete:
            text.append(" — from your library")
        if tracks is not None:
            count = len(tracks)
            text.append(f" — all {count} tracks:\n\n" if count != 1 else " — 1 track:\n\n")
            for item in tracks:
                text.append("  • ")
                text.append(str(item.title or f"item {item.id}"), style=self.TITLE_STYLE)
                if delete and item.path:
                    text.append("\n    ")
                    text.append(os.fsdecode(item.path), style=self.PATH_STYLE)
                text.append("\n")
        else:
            text.append(".\n")
        text.append("\nThe audio files and album art will be deleted from disk "
                    "— this cannot be undone."
                    if delete else
                    "\nThe audio files will stay on disk.")
        return text

    def _describe_retag(self, query: str) -> Text:
        try:
            count = len(library.search(query) if query else library.all_items())
        except Exception:
            count = None
        tracks = f"{count} tracks" if count is not None else "the matching tracks"
        text = Text()
        text.append("Tuney would like to re-tag ")
        if query:
            text.append(tracks, style=self.TITLE_STYLE)
            text.append(" matching ")
            text.append(query, style=self.ALBUM_STYLE)
        else:
            text.append("your ENTIRE library", style=self.TITLE_STYLE)
            if count is not None:
                text.append(f" ({count} tracks)")
        text.append(
            " by looking each album up on MusicBrainz.\n\n"
            "Tracks with a confident match get corrected metadata written to "
            "the library AND to the audio files' own tags; tracks without a "
            "confident match are left untouched.\n\n"
            "This can take a long time on many tracks."
        )
        return text

    def _describe_set_tags(self, item_id, args: dict) -> Text:
        old_title, old_artist, _album, path = self._item_fields(item_id)
        item = self._lookup_item(item_id)
        text = Text()
        text.append("Tuney would like to edit the metadata of ")
        text.append(old_title, style=self.TITLE_STYLE)
        if old_artist:
            text.append(f" by {old_artist}")
        text.append(":\n\n")
        for field in ("title", "artist", "album", "albumartist", "genre", "year"):
            value = args.get(field)
            if not value:
                continue
            old = (item.get(field) if item is not None else None) or "(empty)"
            text.append(f"  {field}: {old} -> ")
            text.append(str(value), style=self.TITLE_STYLE)
            text.append("\n")
        if path:
            text.append("\n  File: ")
            text.append(path, style=self.PATH_STYLE)
        text.append("\n\nThe library entry and the file's own tags will be rewritten.")
        return text

    # Changed fields hidden from the apply_track_tags diff: bookkeeping the
    # user didn't ask about and can't meaningfully review. artists_sort /
    # artists_credit just restate `artists`.
    HIDDEN_TAG_FIELDS = {"mtime", "data_source", "length",
                         "artists_sort", "artists_credit"}
    # Human-relevant fields shown first, in this order; anything else
    # follows alphabetically.
    TAG_FIELD_ORDER = ("title", "artist", "album", "albumartist", "genre",
                       "year", "artist_sort", "artist_credit", "composer",
                       "lyricist", "arranger")

    def _describe_apply_tags(self, item_id, artist: str, title: str,
                             changes: list | None = None,
                             note: str | None = None) -> Text:
        """`changes` is the (field, old, new) diff once fetched; until then a
        one-line summary plus `note` (progress or error) is shown instead."""
        old_title, old_artist, _album, path = self._item_fields(item_id)
        text = Text()
        text.append("Tuney would like to fix the metadata of ")
        text.append(old_title, style=self.TITLE_STYLE)
        if old_artist:
            text.append(f" by {old_artist}")
        text.append(" using MusicBrainz:\n\n")
        if changes is None:
            text.append("  New tags: ")
            text.append(f"{artist} - {title}", style=self.TITLE_STYLE)
            if note:
                text.append(f"\n\n  {note}", style="dim")
        else:
            rows = [(field, old, new) for field, old, new in changes
                    if field not in self.HIDDEN_TAG_FIELDS
                    and not field.startswith("mb_")]
            order = {field: index for index, field in enumerate(self.TAG_FIELD_ORDER)}
            rows.sort(key=lambda row: (order.get(row[0], len(order)), row[0]))
            if not rows:
                text.append("  No visible tag changes — the track already "
                            "matches this recording (MusicBrainz ids may "
                            "still be updated).")
            for field, old, new in rows:
                text.append(f"  {field}: {old or '(empty)'} -> ")
                text.append(str(new), style=self.TITLE_STYLE)
                text.append("\n")
            text.rstrip()
        if path:
            text.append("\n\n  File: ")
            text.append(path, style=self.PATH_STYLE)
        text.append("\n\nThe library entry and the file's own tags will be rewritten.")
        return text

    def compose(self) -> ComposeResult:
        detail = self._describe()
        if detail is None:
            args = ", ".join(f"{k}={v!r}" for k, v in self._request.get("args", {}).items())
            detail = Text(f"{self._request.get('description') or 'Tool requires approval'}\n\n"
                          f"  {self._request.get('name', '?')}({args})")
        title = "Tuney needs your approval"
        if self._total > 1:
            title += f" ({self._position} of {self._total})"
        with Container(id="confirm-dialog"):
            yield Label(title, id="modal-title")
            with VerticalScroll(id="confirm-detail-scroll", can_focus=False):
                yield Static(detail, id="confirm-detail")
            with Horizontal(id="confirm-buttons"):
                yield Button("Approve", id="approve", variant="error")
                yield Button("Approve all", id="approve-all", variant="warning")
                yield Button("Reject", id="reject", variant="primary")
                yield Button("Reject all", id="reject-all", variant="primary")
            yield Label(r"\[y] approve | \[a] approve all this run | "
                        r"\[n]/\[esc] reject | \[r] reject all this run | "
                        r"\[↑↓] scroll", id="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#reject", Button).focus()   # safe default
        if self._request.get("name") == "apply_track_tags":
            self._load_tag_changes()

    @work(thread=True)
    def _load_tag_changes(self) -> None:
        """Fetch the field-by-field diff the MusicBrainz match would write
        and swap it into the dialog (a network lookup, hence off-thread)."""
        args = self._request.get("args", {})
        changes = note = None
        try:
            item = library.get_item(args.get("item_id"))
            if item is None:
                raise ValueError(f"item {args.get('item_id')} not found")
            changes = library.preview_track_match(item, str(args.get("recording_id")))
        except Exception as e:
            note = f"Couldn't fetch the list of changes from MusicBrainz ({e})."
        text = self._describe_apply_tags(args.get("item_id"),
                                         str(args.get("artist") or "?"),
                                         str(args.get("title") or "?"),
                                         changes=changes, note=note)
        self.app.call_from_thread(self._show_detail, text)

    def _show_detail(self, text: Text) -> None:
        try:
            self.query_one("#confirm-detail", Static).update(text)
        except NoMatches:
            pass    # already answered and dismissed while the lookup ran

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve-all":
            self.dismiss("all")
        elif event.button.id == "reject-all":
            self.dismiss("reject_all")
        else:
            self.dismiss(event.button.id == "approve")

    def action_scroll_detail(self, direction: int) -> None:
        scroll = self.query_one("#confirm-detail-scroll", VerticalScroll)
        if direction > 0:
            scroll.scroll_down()
        else:
            scroll.scroll_up()

    def action_scroll_detail_page(self, direction: int) -> None:
        scroll = self.query_one("#confirm-detail-scroll", VerticalScroll)
        if direction > 0:
            scroll.scroll_page_down()
        else:
            scroll.scroll_page_up()

    def action_approve(self) -> None:
        self.dismiss(True)

    def action_approve_all(self) -> None:
        self.dismiss("all")

    def action_reject_all(self) -> None:
        self.dismiss("reject_all")

    def action_reject(self) -> None:
        self.dismiss(False)
