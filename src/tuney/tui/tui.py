from textual.app import App
from .Screens.MenuScreen import MenuScreen

class TuneyApp(App):
    # CSS = "DataTable { height: 1fr; } .hidden { display: none; }"

    TITLE = "TUNEY"

    def on_mount(self) -> None:
        self.push_screen(MenuScreen())

if __name__ == "__main__":
    TuneyApp().run()