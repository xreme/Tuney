from textual.containers import Vertical


class Pane(Vertical):
    """A tile in the workspace: a screen's worth of UI as a widget.

    Subclasses set PANE_NAME (the registry key and border title) and override
    focus_pane() to focus their preferred inner widget.
    """

    ALLOW_MAXIMIZE = True
    PANE_NAME = "pane"

    DEFAULT_CSS = """
    Pane {
        border: round $panel;
    }
    Pane:focus-within {
        border: round $accent;
    }
    """

    def __init__(self, leaf=None) -> None:
        super().__init__()
        self.leaf = leaf                # the layout-tree node this pane renders
        self.border_title = self.PANE_NAME

    def focus_pane(self) -> None:
        """Focus this pane's preferred widget."""
        for child in self.query("*"):
            if child.focusable:
                child.focus()
                return
