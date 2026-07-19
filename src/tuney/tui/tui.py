import subprocess
import sys

from textual.app import App
from textual.binding import Binding
from .Screens.WorkspaceScreen import WorkspaceScreen

class TuneyApp(App):
    TITLE = "TUNEY"

    ansi_color = True

    BINDINGS = [Binding("ctrl+q", "quit", "Quit", show=False)]

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=False)

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.push_screen(WorkspaceScreen())

if __name__ == "__main__":
    TuneyApp().run()
