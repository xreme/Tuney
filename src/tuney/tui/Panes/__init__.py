from .base import Pane
from .CollectionPane import CollectionPane
from .ChatPane import ChatPane
from .SettingsPane import SettingsPane
from .StatsBar import StatsBar

# The pane registry: layout-tree pane names → widget classes. This is the
# single source of truth for what panes exist — the layout validator and the
# pane chooser both derive from it, so adding a pane here is all it takes.
PANE_TYPES = {
    "collection": CollectionPane,
    "chat": ChatPane,
    "settings": SettingsPane,
}


def pane_names() -> frozenset[str]:
    """Every valid pane key (for validating serialized layouts)."""
    return frozenset(PANE_TYPES)


def pane_choices() -> list[tuple[str, str]]:
    """(key, display label) for each pane, in registration order — used to
    populate the pane chooser. The label comes from the class's PANE_NAME."""
    return [(key, cls.PANE_NAME) for key, cls in PANE_TYPES.items()]
