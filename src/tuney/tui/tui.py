from textual.app import App
from .Screens.MenuScreen import MenuScreen

class TuneyApp(App):
    # CSS = "DataTable { height: 1fr; } .hidden { display: none; }"

    TITLE = "TUNEY"

    ansi_color = True

    def on_mount(self) -> None:
        self.theme = "ansi-dark"
        self.push_screen(MenuScreen())

if __name__ == "__main__":
    TuneyApp().run()