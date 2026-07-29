from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label

from tuney import library
from tuney.wishlist import Wishlist
from tuney.tui.Modals.WishlistFormModal import WishlistFormModal


class WishlistEditModal(WishlistFormModal):
    """Edit an existing wishlist item — the same fields as the add form,
    prefilled from the row, saved back through `update_item`."""

    CSS = """
    WishlistEditModal { align: center middle; }
    #edit-dialog {
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    #edit-title {
        width: 100%;
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
    }
    #edit-buttons { height: auto; align-horizontal: center; padding-top: 1; }
    #edit-buttons Button { margin: 0 1; }
    #edit-hint { width: 100%; text-align: center; padding-top: 1; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, item: dict) -> None:
        super().__init__()
        self._item = item

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label("Edit wishlist item", id="edit-title")
            yield from self.compose_fields(self._item)
            with Horizontal(id="edit-buttons"):
                yield Button("Save", id="save", variant="primary")
                yield Button("Cancel", id="cancel")
            yield Label(r"\[Save] update · \[esc] cancel", id="edit-hint")

    def on_mount(self) -> None:
        self.query_one("#f-artist").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = {
            "save": self.action_save,
            "cancel": self.action_cancel,
        }.get(event.button.id)
        if handler is not None:
            handler()

    def action_save(self) -> None:
        fields = self._collect()
        if not (fields["artist"] or fields["title"]):
            self.notify("A wishlist item needs at least an artist or title.",
                        severity="warning")
            return
        try:
            with Wishlist(library.DB) as wishlist:
                wishlist.update_item(self._item["id"], fields)
        except Exception as error:
            self.notify(f"Could not save item: {error}", severity="error")
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(None)
