import json

from langchain.tools import tool

from tuney import library
from tuney.wishlist import Wishlist


# A serialized wishlist item is small, but the list is unbounded; cap results
# so one dump can't blow the model's context window (mirrors tools.py).
_MAX_RESULTS = 100

# Fields the user can set when adding or editing a wishlist item. `id`,
# `date_added`, `date_updated`, and `acquired_id` are managed by the data layer.
_EDITABLE_FIELDS = ("artist", "title", "album", "year", "mb_id", "notes",
                    "priority", "status")


# One shared connection to the canonical wishlist DB, opened lazily so importing
# this module (e.g. at agent build time) never touches the disk or fails.
_wishlist: Wishlist | None = None


def _wl() -> Wishlist:
    global _wishlist
    if _wishlist is None:
        _wishlist = Wishlist(library.DB)
    return _wishlist


def _rows(items) -> list[dict]:
    """The data layer's list methods are stubs today and may return None;
    treat None as an empty wishlist so read tools don't crash before the
    owner implements wishlist.py."""
    return list(items) if items else []


def _capped(items: list[dict]) -> list[str]:
    """Serialize items as JSON strings, with a trailing note when the list is
    truncated so the model knows more exist and can narrow its request."""
    rows = _rows(items)
    page = [json.dumps(row) for row in rows[:_MAX_RESULTS]]
    if len(rows) > _MAX_RESULTS:
        page.append(json.dumps({
            "truncated": True,
            "total_matches": len(rows),
            "shown": _MAX_RESULTS,
            "note": (f"Showing the first {_MAX_RESULTS} of {len(rows)} items. "
                     "Use search_wishlist to narrow down to specific items."),
        }))
    return page


@tool
def list_wishlist():
    """List every item on the user's wishlist as JSON objects.

    A wishlist item is music the user WANTS but doesn't own yet. Each object
    has: id, artist, title, album, year, date_added, date_updated, mb_id,
    notes, priority, status, acquired_id. An empty list means the wishlist is
    empty. Results are capped at 100 with a trailing note when more exist —
    prefer `search_wishlist` when the user is after something specific.
    """
    return _capped(_wl().all_items())


@tool
def search_wishlist(query: str):
    """Search the user's wishlist by a case-insensitive substring.

    Matches `query` against each item's artist, title, album, notes, and
    status, returning the matching items as JSON objects (same shape as
    `list_wishlist`). An empty list means nothing matched — try a shorter or
    differently spelled fragment before concluding the item isn't wishlisted.
    Results are capped at 100.
    """
    needle = query.strip().lower()
    matches = [
        item for item in _rows(_wl().all_items())
        if any(needle in str(item.get(field, "") or "").lower()
               for field in ("artist", "title", "album", "notes", "status"))
    ]
    return _capped(matches)


@tool
def wishlist_item_information(item_id: int):
    """Retrieve one wishlist item by its id, as a JSON object.

    Returns all fields (artist, title, album, year, mb_id, notes, priority,
    status, date_added, date_updated, acquired_id), or a message if no item
    has that id. Use it to confirm the right target before updating or
    removing an item.
    """
    item = _wl().get_item(item_id)
    if item is None:
        return f"No wishlist item found with id {item_id}"
    return json.dumps(item)


@tool
def add_wishlist_item(artist: str, title: str, album: str = "",
                      year: int | None = None, notes: str = "",
                      priority: int = 0, status: str = "wanted",
                      mb_id: str = ""):
    """Add a track or release the user wants to their wishlist.

    Pass at least an artist and title. `mb_id` links the item to a specific
    MusicBrainz recording — when the user wants an exact release, first call
    `match_wishlist_musicbrainz` to get candidates, pick the right one, and
    pass its `mb_id` here so the item is unambiguous. `priority` is a number
    (higher = more wanted); `status` defaults to "wanted". This is additive
    and needs no confirmation.

    Returns the new item's id.
    """
    new_id = _wl().add_item(
        artist=artist, title=title, album=album, year=year,
        mb_id=mb_id, notes=notes, priority=priority, status=status,
    )
    return f"Added wishlist item {new_id}: {artist} - {title}"


@tool
def match_wishlist_musicbrainz(artist: str, title: str, album: str = ""):
    """Look up MusicBrainz candidates for a track the user wants to wishlist.
    Read-only — nothing is added.

    Returns up to 5 candidate JSON objects (mb_id, artist, title, album, year,
    score), best match first, where score is 0..1 (1.0 = perfect). Pick the
    candidate that matches the user's intent, then call `add_wishlist_item`
    with its `mb_id` so the wishlist item points at an exact release. An empty
    list means MusicBrainz returned nothing — try different or fuller
    artist/title spelling before giving up.
    """
    candidates = library.musicbrainz_candidates(
        artist=artist, title=title, album=album, limit=5)
    return json.dumps(candidates)


@tool
def update_wishlist_item(item_id: int, artist: str = "", title: str = "",
                         album: str = "", year: int | None = None,
                         notes: str = "", priority: int | None = None,
                         status: str = "", mb_id: str = ""):
    """Edit fields on an existing wishlist item, looked up by id.

    Only the fields you pass are changed: an empty string (or None for year
    and priority) leaves that field untouched, so this cannot blank out a
    field. Common edits: bumping `priority`, changing `status` (e.g. "wanted"
    -> "ordered"), or adding `notes`. Verify the id with
    `wishlist_item_information` first. This is additive and needs no
    confirmation.

    Returns a summary of what changed, or a message if the id doesn't exist
    or no fields were given.
    """
    if _wl().get_item(item_id) is None:
        return f"No wishlist item found with id {item_id}"

    requested = {"artist": artist, "title": title, "album": album,
                 "year": year, "notes": notes, "priority": priority,
                 "status": status, "mb_id": mb_id}
    fields = {name: value for name, value in requested.items()
              if name in _EDITABLE_FIELDS and value not in ("", None)}
    if not fields:
        return ("No fields given — pass at least one of "
                f"{', '.join(_EDITABLE_FIELDS)}.")

    _wl().update_item(item_id, fields)
    changes = ", ".join(f"{name}={value!r}" for name, value in fields.items())
    return f"Updated wishlist item {item_id}: {changes}"


@tool
def remove_wishlist_item(item_id: int):
    """Remove a single item from the user's wishlist, looked up by id.

    Only touches the wishlist — it never affects the user's music library or
    any files on disk. Calling this tool automatically shows the user a
    confirmation dialog; nothing is removed until they approve, so do NOT ask
    for permission in chat first. Verify the id refers to the item the user
    means (via `wishlist_item_information`) before calling.

    Returns a message confirming the removal, or a message if the id doesn't
    exist.
    """
    item = _wl().get_item(item_id)
    if item is None:
        return f"No wishlist item found with id {item_id}"
    _wl().remove_item(item_id)
    return (f"Removed wishlist item {item_id}: "
            f"{item.get('artist', '')} - {item.get('title', '')}")


@tool
def clear_wishlist():
    """Remove EVERY item from the user's wishlist. This cannot be undone.

    Only touches the wishlist — it never affects the user's music library or
    files on disk. Calling this tool automatically shows the user a
    confirmation dialog; nothing is cleared until they approve, so do NOT ask
    for permission in chat first. Prefer `remove_wishlist_item` when the user
    only wants specific items gone.

    Returns a message confirming the wishlist was cleared.
    """
    _wl().clear_wishlist()
    return "Cleared the wishlist — all items removed."
