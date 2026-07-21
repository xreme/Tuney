from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Header, Footer, Static

from tuney import config
from tuney.tui import layout
from tuney.tui.layout import PaneLeaf, Split
from tuney.tui.Modals import ScanModal
from tuney.tui.Modals.PaneChooserModal import PaneChooserModal
from tuney.tui.Panes import PANE_TYPES, Pane, CollectionPane, StatsBar, pane_names


class WorkspaceScreen(Screen):
    """The tiling workspace: every view lives in a pane the user can split,
    close, zoom and rearrange, tmux-style. The layout persists in config."""

    CSS = """
    #tiles { height: 1fr; }
    #empty-hint {
        width: 1fr;
        height: 1fr;
        content-align: center middle;
        color: $text-muted;
    }
    """

    # ctrl+letter combos work out of the box in every macOS terminal; the
    # alt+ variants are kept as aliases for terminals with option-as-meta.
    BINDINGS = [
        Binding("ctrl+t,alt+d", "split('row')", "Split →"),
        Binding("ctrl+b,alt+s", "split('col')", "Split ↓"),
        Binding("ctrl+r,alt+x", "close_pane", "Close pane"),
        Binding("ctrl+f,alt+z", "toggle_zoom", "Zoom"),
        Binding("ctrl+o", "focus_next", "Next pane"),
        Binding("ctrl+g", "change_pane", "Change pane"),
        Binding("alt+left", "focus_dir('left')", "Focus left", show=False),
        Binding("alt+right", "focus_dir('right')", "Focus right", show=False),
        Binding("alt+up", "focus_dir('up')", "Focus up", show=False),
        Binding("alt+down", "focus_dir('down')", "Focus down", show=False),
        Binding("alt+shift+left", "resize('row', -0.05)", "Shrink", show=False),
        Binding("alt+shift+right", "resize('row', 0.05)", "Grow", show=False),
        Binding("alt+shift+up", "resize('col', -0.05)", "Shrink", show=False),
        Binding("alt+shift+down", "resize('col', 0.05)", "Grow", show=False),
        Binding("alt+1", "set_pane('collection')", "Collection here", show=False),
        Binding("alt+2", "set_pane('chat')", "Chat here", show=False),
        Binding("alt+3", "set_pane('settings')", "Settings here", show=False),
        Binding("ctrl+n,alt+n", "scan", "Scan"),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatsBar()
        yield Container(id="tiles")
        yield Footer()

    def on_mount(self) -> None:
        self._save_timer = None
        saved = config.get_config().workspace_layout
        self.root = (layout.from_dict(saved, pane_names()) if saved is not None
                     else layout.default_layout())
        tiles = self.query_one("#tiles")
        tiles.mount(self._build_node(self.root))
        self.call_after_refresh(self._focus_leaf, next(layout.iter_leaves(self.root)))

    def on_screen_resume(self) -> None:
        """A modal just closed (scan, confirm, chooser) — the library may
        have changed under us."""
        self._refresh_library()

    def on_chat_pane_agent_run_finished(self, _message) -> None:
        """The agent finished a run; deletions/imports it made should show."""
        self._refresh_library()

    def _refresh_library(self) -> None:
        self.query_one(StatsBar).refresh_stats()
        for pane in self.query(CollectionPane):
            pane.reload()

    # ---- tree → widgets ----------------------------------------------------

    def _build_node(self, node) -> Widget:
        if isinstance(node, PaneLeaf):
            pane = PANE_TYPES[node.pane](leaf=node)
            pane.id = f"pane-{node.node_id}"
            return pane
        first = self._build_node(node.first)
        second = self._build_node(node.second)
        container_cls = Horizontal if node.direction == "row" else Vertical
        container = container_cls(first, second, id=f"split-{node.node_id}")
        self._apply_ratio(node, first, second)
        return container

    def _apply_ratio(self, split: Split, first: Widget, second: Widget) -> None:
        if split.direction == "row":
            first.styles.width = f"{split.ratio * 100:.1f}%"
            second.styles.width = "1fr"
        else:
            first.styles.height = f"{split.ratio * 100:.1f}%"
            second.styles.height = "1fr"

    def _widget_for(self, node) -> Widget:
        prefix = "pane" if isinstance(node, PaneLeaf) else "split"
        return self.query_one(f"#{prefix}-{node.node_id}")

    async def _swap_in(self, node, old_widget: Widget) -> Widget:
        """Replace `old_widget` with a freshly built subtree for `node`,
        keeping its slot (and its slot's share of the split) in the layout."""
        parent_widget = old_widget.parent
        # Remove before mounting: the rebuilt subtree reuses the old ids.
        position = parent_widget.children.index(old_widget)
        await old_widget.remove()
        new_widget = self._build_node(node)
        parent_node = layout.find_parent(self.root, node)
        if parent_node is not None:
            sibling_node = (parent_node.second if parent_node.first is node
                            else parent_node.first)
            first, second = ((new_widget, self._widget_for(sibling_node))
                             if parent_node.first is node
                             else (self._widget_for(sibling_node), new_widget))
            self._apply_ratio(parent_node, first, second)
        if position < len(parent_widget.children):
            await parent_widget.mount(new_widget, before=position)
        else:
            await parent_widget.mount(new_widget)
        return new_widget

    def _save_layout(self) -> None:
        cfg = config.get_config()
        cfg.workspace_layout = (layout.to_dict(self.root)
                                if self.root is not None else None)
        cfg.save()

    # ---- empty workspace ---------------------------------------------------

    def _show_empty_hint(self) -> None:
        self.query_one("#tiles").mount(
            Static("No panes open — press ctrl+g to open one.", id="empty-hint"))

    async def _prompt_for_pane(self) -> None:
        """The workspace is empty; offer the pane types. Backing out leaves
        the empty hint on screen — ctrl+g reopens the chooser."""
        choice = await self.app.push_screen_wait(PaneChooserModal("Open a pane…"))
        if choice is not None:
            await self._open_root_pane(choice)

    async def _open_root_pane(self, choice: str) -> None:
        leaf = PaneLeaf(choice)
        self.root = leaf
        for hint in self.query("#empty-hint"):
            await hint.remove()
        await self.query_one("#tiles").mount(self._build_node(leaf))
        self._save_layout()
        self.call_after_refresh(self._focus_leaf, leaf)

    def _save_layout_soon(self) -> None:
        """Resizing arrives as a burst of repeated keystrokes; write the
        layout once the burst settles instead of once per keypress."""
        if self._save_timer is not None:
            self._save_timer.stop()
        self._save_timer = self.set_timer(0.5, self._save_layout)

    # ---- focus helpers -----------------------------------------------------

    def _focused_pane(self) -> Pane | None:
        node = self.focused
        while node is not None and not isinstance(node, Pane):
            node = node.parent
        if node is None:
            panes = list(self.query(Pane))
            return panes[0] if panes else None
        return node

    def _focus_leaf(self, leaf: PaneLeaf) -> None:
        try:
            self._widget_for(leaf).focus_pane()
        except Exception:
            pass

    # ---- actions -----------------------------------------------------------

    @work
    async def action_split(self, direction: str) -> None:
        if self.root is None:
            await self._prompt_for_pane()
            return
        pane = self._focused_pane()
        if pane is None or pane.leaf is None:
            return
        arrow = "→" if direction == "row" else "↓"
        choice = await self.app.push_screen_wait(PaneChooserModal(f"Split {arrow} with…"))
        if choice is None or not self._allow_pane(choice):
            return
        leaf = pane.leaf
        self.root, new_leaf = layout.split_leaf(self.root, leaf, direction, choice)
        split_node = layout.find_parent(self.root, new_leaf)
        await self._swap_in(split_node, pane)
        self._save_layout()
        self.call_after_refresh(self._focus_leaf, new_leaf)

    # Panes that may exist only once in the workspace: a second chat pane would
    # share the same agent conversation/transcript, and a second wishlist pane
    # is redundant (and both would fight over the same wishlist DB from
    # different threads).
    _SINGLETON_PANES = {"chat", "wishlist"}

    def _allow_pane(self, choice: str) -> bool:
        if choice in self._SINGLETON_PANES and self.query(PANE_TYPES[choice]):
            self.notify(f"Only one {choice} pane at a time.", severity="warning")
            return False
        return True

    @work
    async def action_close_pane(self) -> None:
        pane = self._focused_pane()
        if pane is None or pane.leaf is None:
            return
        parent = layout.find_parent(self.root, pane.leaf)
        if parent is None:
            # Last pane: the workspace goes empty and the chooser offers a
            # fresh start.
            self.root = None
            await pane.remove()
            self._save_layout()
            self._show_empty_hint()
            await self._prompt_for_pane()
            return
        sibling = parent.second if parent.first is pane.leaf else parent.first
        split_widget = self._widget_for(parent)
        self.root = layout.remove_leaf(self.root, pane.leaf)
        new_widget = await self._swap_in(sibling, split_widget)
        self._save_layout()
        self.call_after_refresh(self._focus_leaf, next(layout.iter_leaves(sibling)))

    def action_focus_next(self) -> None:
        panes = list(self.query(Pane))
        if len(panes) < 2:
            return
        current = self._focused_pane()
        panes[(panes.index(current) + 1) % len(panes)].focus_pane()

    @work
    async def action_change_pane(self) -> None:
        if self.root is None:
            await self._prompt_for_pane()
            return
        pane = self._focused_pane()
        if pane is None or pane.leaf is None:
            return
        choice = await self.app.push_screen_wait(
            PaneChooserModal("Change this pane to…"))
        if choice is not None:
            self.action_set_pane(choice)

    @work
    async def action_set_pane(self, choice: str) -> None:
        if self.root is None:
            await self._open_root_pane(choice)
            return
        pane = self._focused_pane()
        if pane is None or pane.leaf is None:
            return
        if pane.leaf.pane == choice or not self._allow_pane(choice):
            return
        pane.leaf.pane = choice
        await self._swap_in(pane.leaf, pane)
        self._save_layout()
        self.call_after_refresh(self._focus_leaf, pane.leaf)

    def action_toggle_zoom(self) -> None:
        if self.maximized:
            self.minimize()
            return
        pane = self._focused_pane()
        if pane is not None:
            self.maximize(pane)

    def action_focus_dir(self, direction: str) -> None:
        current = self._focused_pane()
        if current is None:
            return
        cx, cy = current.region.center
        best = None
        best_score = None
        for pane in self.query(Pane):
            if pane is current:
                continue
            px, py = pane.region.center
            dx, dy = px - cx, py - cy
            along, across = {
                "left": (-dx, dy), "right": (dx, dy),
                "up": (-dy, dx), "down": (dy, dx),
            }[direction]
            if along <= 0:          # not in that direction
                continue
            score = along + 2 * abs(across)
            if best_score is None or score < best_score:
                best, best_score = pane, score
        if best is not None:
            best.focus_pane()

    def action_resize(self, axis: str, delta: float) -> None:
        pane = self._focused_pane()
        if pane is None or pane.leaf is None:
            return
        # The nearest ancestor split along this axis is the one to resize.
        node = pane.leaf
        parent = layout.find_parent(self.root, node)
        while parent is not None and parent.direction != axis:
            node = parent
            parent = layout.find_parent(self.root, parent)
        if parent is None:
            return
        # Growing always means "give my side more room".
        grow = delta if parent.first is node else -delta
        parent.ratio = min(layout.MAX_RATIO, max(layout.MIN_RATIO, parent.ratio + grow))
        split_widget = self._widget_for(parent)
        children = list(split_widget.children)
        self._apply_ratio(parent, children[0], children[1])
        self._save_layout_soon()

    def action_scan(self) -> None:
        self.app.push_screen(ScanModal())
