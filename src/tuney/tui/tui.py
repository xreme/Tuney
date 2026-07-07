import subprocess
import sys

from textual.app import App
from .Screens.MenuScreen import MenuScreen

class TuneyApp(App):
    # CSS = "DataTable { height: 1fr; } .hidden { display: none; }"

    TITLE = "TUNEY"

    ansi_color = True

    def copy_to_clipboard(self, text: str) -> None:
        super().copy_to_clipboard(text)
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=False)

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.push_screen(MenuScreen())

if __name__ == "__main__":
    TuneyApp().run()