from .base import Pane
from .CollectionPane import CollectionPane
from .ChatPane import ChatPane
from .SettingsPane import SettingsPane
from .StatsBar import StatsBar

# Layout-tree pane names → widget classes.
PANE_TYPES = {
    "collection": CollectionPane,
    "chat": ChatPane,
    "settings": SettingsPane,
}
