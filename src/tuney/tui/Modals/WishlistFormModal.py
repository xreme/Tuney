from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class WishlistFormModal(ModalScreen):
    """Shared field form for adding or editing a wishlist item.

    Provides the labelled inputs and the helpers to read, prefill, and collect
    them. Subclasses lay out the surrounding dialog, add buttons, and decide
    what happens on save. Inputs get ids `#f-<key>`; a subclass that wants the
    status line must include a `Static` with id `#form-status`.
    """

    DEFAULT_CSS = """
    WishlistFormModal #form-fields { height: auto; max-height: 24; }
    WishlistFormModal #form-fields Label { padding: 0 1; color: $text-muted; }
    WishlistFormModal #form-fields Input { margin-bottom: 1; }
    WishlistFormModal #form-status {
        width: 100%; text-align: center; color: $text-muted;
    }
    """

    # (field key, label, placeholder) for each text input, in display order.
    # Kept deliberately minimal — a wishlist entry is just a song. mb_id/year
    # come from a MusicBrainz match, and status/priority are managed elsewhere.
    FIELDS = [
        ("artist", "Artist", "Artist"),
        ("title", "Title", "Title"),
        ("album", "Album", "Album"),
        ("notes", "Notes", "Notes"),
    ]

    def compose_fields(self, values: dict | None = None):
        """Yield the labelled inputs, optionally prefilled from `values`."""
        values = values or {}
        with VerticalScroll(id="form-fields"):
            for key, label, placeholder in self.FIELDS:
                yield Label(label)
                raw = values.get(key)
                yield Input(
                    value="" if raw is None or raw == "" else str(raw),
                    placeholder=placeholder,
                    id=f"f-{key}",
                )

    def _value(self, key: str) -> str:
        return self.query_one(f"#f-{key}", Input).value.strip()

    def _set(self, key: str, value) -> None:
        self.query_one(f"#f-{key}", Input).value = (
            "" if value is None else str(value))

    def _status(self, message: str) -> None:
        self.query_one("#form-status", Static).update(message)

    def _collect(self) -> dict:
        """The visible field values as a wishlist-shaped dict."""
        return {key: self._value(key) for key, _, _ in self.FIELDS}
