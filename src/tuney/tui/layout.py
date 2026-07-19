"""The workspace layout: a binary tree of splits with panes at the leaves.

Pure data — no Textual imports — so it can be serialized into the config
and unit-tested on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

_ids = count(1)


def _next_id() -> int:
    return next(_ids)


@dataclass
class PaneLeaf:
    pane: str                                   # "collection" | "chat" | "settings"
    node_id: int = field(default_factory=_next_id)


@dataclass
class Split:
    direction: str                              # "row" = side by side, "col" = stacked
    ratio: float                                # fraction given to the first child
    first: "Node"
    second: "Node"
    node_id: int = field(default_factory=_next_id)


Node = PaneLeaf | Split

MIN_RATIO = 0.1
MAX_RATIO = 0.9


def default_layout() -> Node:
    return PaneLeaf("collection")


def to_dict(node: Node) -> dict:
    if isinstance(node, PaneLeaf):
        return {"type": "pane", "pane": node.pane}
    return {
        "type": "split",
        "dir": node.direction,
        "ratio": node.ratio,
        "a": to_dict(node.first),
        "b": to_dict(node.second),
    }


def from_dict(data) -> Node:
    """Rebuild a tree from config JSON; any malformed input falls back to
    the default single-pane layout rather than crashing the app."""
    try:
        return _parse(data)
    except (KeyError, TypeError, ValueError):
        return default_layout()


def _parse(data) -> Node:
    if data["type"] == "pane":
        pane = data["pane"]
        if pane not in ("collection", "chat", "settings"):
            raise ValueError(pane)
        return PaneLeaf(pane)
    if data["type"] == "split":
        direction = data["dir"]
        if direction not in ("row", "col"):
            raise ValueError(direction)
        ratio = min(MAX_RATIO, max(MIN_RATIO, float(data["ratio"])))
        return Split(direction, ratio, _parse(data["a"]), _parse(data["b"]))
    raise ValueError(data["type"])


def iter_leaves(node: Node):
    if isinstance(node, PaneLeaf):
        yield node
    else:
        yield from iter_leaves(node.first)
        yield from iter_leaves(node.second)


def find_parent(root: Node, target: Node) -> Split | None:
    """The split whose first/second is `target`, or None for the root."""
    if isinstance(root, Split):
        if root.first is target or root.second is target:
            return root
        return find_parent(root.first, target) or find_parent(root.second, target)
    return None


def split_leaf(root: Node, leaf: PaneLeaf, direction: str, new_pane: str) -> tuple[Node, PaneLeaf]:
    """Replace `leaf` with a split holding it and a new pane; returns the
    (possibly new) root and the freshly created leaf."""
    new_leaf = PaneLeaf(new_pane)
    replacement = Split(direction, 0.5, leaf, new_leaf)
    return _replace(root, leaf, replacement), new_leaf


def remove_leaf(root: Node, leaf: PaneLeaf) -> Node | None:
    """Remove `leaf`; its parent split collapses into the sibling. Removing
    the root leaf empties the tree (returns None)."""
    parent = find_parent(root, leaf)
    if parent is None:
        return None if root is leaf else root
    sibling = parent.second if parent.first is leaf else parent.first
    return _replace(root, parent, sibling)


def _replace(root: Node, target: Node, replacement: Node) -> Node:
    if root is target:
        return replacement
    if isinstance(root, Split):
        if root.first is target:
            root.first = replacement
        elif root.second is target:
            root.second = replacement
        else:
            _replace(root.first, target, replacement)
            _replace(root.second, target, replacement)
    return root
