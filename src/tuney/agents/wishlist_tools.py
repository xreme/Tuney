import json

from langchain.tools import tool

from tuney import lastfm, library
from tuney.agents import activity
from tuney.wishlist import Wishlist


# A serialized wishlist item is small, but the list is unbounded; cap results
# so one dump can't blow the model's context window (mirrors tools.py).
_MAX_RESULTS = 100

# A discography listing is capped rather than paged: nobody is choosing from
# an artist's 200th best-known release.
_MAX_ALBUMS = 25

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
    `search_music` to get candidates, pick the right one, and pass its `mb_id`
    here so the item is unambiguous (leave it empty for a Last.fm result, which
    has no recording id). `priority` is a number (higher =
    more wanted); `status` defaults to "wanted". This is additive and needs no
    confirmation. To add several tracks at once (e.g. a whole album), use
    `add_wishlist_items` instead of calling this repeatedly.

    Returns the created item as a JSON object (including its new `id`, `artist`,
    `title`, and `album`) — relay those exact values; don't restate them from
    memory. It also carries `already_owned`: the collection track id when the
    user turns out to own this song already, otherwise null. A single add is a
    deliberate one, so the item is added either way — but when `already_owned`
    is set, tell the user they already have it rather than reporting a clean
    add. (`add_wishlist_items` skips owned tracks instead, since a whole-album
    add is rarely meant to re-add music they have.)
    """
    new_id = _wl().add_item(
        artist=artist, title=title, album=album, year=year,
        mb_id=mb_id, notes=notes, priority=priority, status=status,
    )
    [beets_id] = library.owned_ids([
        {"artist": artist, "title": title, "mb_id": mb_id}])
    # Ungated, so nothing else tells the UI the run did real work.
    activity.record_change()
    return json.dumps(dict(_wl().get_item(new_id), already_owned=beets_id))


@tool
def add_wishlist_items(items: list[dict], skip_owned: bool = True):
    """Add several wanted tracks to the wishlist in one call — use this for a
    whole album or any multi-track add instead of calling `add_wishlist_item`
    repeatedly.

    `items` is a list of objects, each with at least `artist` and `title` and
    optionally `album`, `year`, `mb_id`, `notes`, `priority`, and `status`
    (unknown keys are ignored; `status` defaults to "wanted"). When wishlisting
    an album from `search_music`, pass the chosen release's `tracks` entries
    straight through — each already carries its own `mb_id` (empty for a
    Last.fm album), `title`, `album`, and `year`. This is additive and needs no
    confirmation.

    Every track is checked against the user's collection first. By default the
    ones they already own are NOT added (`skip_owned`) — a wishlist is for
    music they don't have. Pass skip_owned=false only when the user knowingly
    wants an owned track wishlisted anyway (wanting it on vinyl, or in a better
    format).

    Returns a JSON object:
        {"added": [full item objects with their new ids],
         "already_owned": [{artist, title, album, beets_id, added}],
         "skipped_owned": true|false}
    Both lists are ground truth — relay their exact titles and ids and never
    fill any in from memory. `already_owned` is not a failure and must not be
    hidden from the user: it is the answer to "do I have this already", so
    report what was skipped and why. An empty `added` with a full
    `already_owned` means they own every track you tried to add — say so
    plainly instead of reporting an add that did not happen.
    """
    entries = [item for item in items
               if (item.get("artist") or item.get("title"))]
    # One collection scan for the whole batch, not one per track.
    owned = library.owned_ids(entries)

    created, already_owned = [], []
    for entry, beets_id in zip(entries, owned):
        if beets_id is not None:
            already_owned.append({
                "artist": entry.get("artist", ""),
                "title": entry.get("title", ""),
                "album": entry.get("album", ""),
                "beets_id": beets_id,
                "added": not skip_owned,
            })
            if skip_owned:
                continue
        fields = {name: entry[name] for name in _EDITABLE_FIELDS if name in entry}
        new_id = _wl().add_item(**fields)
        created.append(_wl().get_item(new_id))

    # A batch where every track was skipped changed nothing.
    if created:
        activity.record_change()

    return json.dumps({
        "added": created,
        "already_owned": already_owned,
        "skipped_owned": bool(skip_owned),
    })


@tool
def collection_has(artist: str, album: str = "", title: str = ""):
    """Check what the user ALREADY OWNS by an artist — the only way to know
    whether something is in their music collection. Read-only.

    The wishlist and the collection are different things, and none of the other
    tools here can see the collection: `search_music` searches MusicBrainz and
    Last.fm (the whole world's music, not the user's), and `search_wishlist`
    only searches the wishlist. So any claim that the user does or does not own
    something must come from THIS tool. Never answer "you don't have that yet"
    from your own knowledge of an artist's discography.

    Pass `artist` alone to get everything they own by them. Add `album` to ask
    about one release, or `title` to ask about one song.

    Returns a JSON object:
        {artist, owned_tracks, albums: {album name: tracks owned, ...},
         album_check?: {asked, owned, matched_album, tracks_owned, related},
         track_check?: {asked, owned, beets_id, matches}}
    `albums` is the COMPLETE list for that artist — every album, never
    paginated or truncated — so to find a release they don't own, compare
    candidates from `artist_top_albums` or `search_music` against it. An empty
    `albums` with `owned_tracks` 0 means they own nothing by that artist.

    In `album_check`, `owned` is true only on a real name match; `related`
    lists albums whose name overlaps the one asked about (editions and
    reissues — "6 (Deluxe Edition)" against "6"). A non-empty `related` with
    `owned` false means "probably a different pressing of something they have"
    — say that rather than calling the album missing.
    """
    albums = library.collection_albums(artist)
    result = {
        "artist": artist,
        "owned_tracks": sum(albums.values()),
        "albums": albums,
    }
    if album:
        found = library.match_album(albums, album)
        result["album_check"] = {
            "asked": album,
            "owned": found["exact"] is not None,
            "matched_album": found["exact"][0] if found["exact"] else None,
            "tracks_owned": found["exact"][1] if found["exact"] else 0,
            "related": found["related"],
        }
    if title:
        matches = library.find_tracks(artist, title)
        result["track_check"] = {
            "asked": title,
            "owned": bool(matches),
            "beets_id": matches[0]["id"] if matches else None,
            "matches": matches,
        }
    return json.dumps(result)


@tool
def search_music(artist: str = "", title: str = "", album: str = "",
                 kind: str = "single"):
    """Search the music metadata sources for music the user might want to
    wishlist — either singles (individual recordings) or whole albums
    (releases). Read-only; nothing is added.

    MusicBrainz and Last.fm are searched together and come back as ONE ranked
    list, best first — there is no per-source call to make and no reason to
    search twice. Every result carries `source`:
    - "musicbrainz" — carries `mb_id`, the id the wishlist stores, and for
      albums an authoritative tracklist. Singles also carry `score` (0..1,
      1.0 = a perfect match).
    - "lastfm" — carries `listeners`, `playcount` and `tags` (listener-supplied
      genre/mood), and covers releases MusicBrainz never catalogued. Its
      `mb_id` is usually empty; that is normal, so add the item without one
      rather than inventing or borrowing an id.

    kind="single" (the default): search recordings by artist/title (pass an
    album too to disambiguate). Returns up to 5 candidates:
        {source, mb_id, artist, title, album, year, score?, listeners?,
         playcount?, tags?}
    Pick the one matching the user's intent and pass its `mb_id` to
    `add_wishlist_item` so the item points at an exact recording.

    kind="album": search releases by artist/album. Returns up to 5 albums, each
    with its tracklist:
        {source, mb_id (release id), album, artist, year, track_count,
         tracks: [{mb_id (recording id), artist, title, album, year}, ...],
         listeners?, playcount?, tags?}
    The wishlist stores individual songs, not albums — so to wishlist a whole
    album, pass its whole `tracks` list to `add_wishlist_items` in one call; to
    wishlist one song from it, add just that track. Albums carry no score
    (each source's own ranking is used). A `track_count` of 0 means that source
    has no tracklist for the release: pick another result for the same album
    rather than adding songs you filled in yourself.

    Last.fm is optional: with no API key configured the results are MusicBrainz
    only, which is not an error. An empty list means nothing matched on any
    source — retry with different or fuller spelling before giving up.
    """
    if kind.strip().lower().startswith("album"):
        albums = library.search_albums(artist=artist, album=album, limit=5)
        for entry in albums:
            # Fill in any tracklist the source didn't ship with its search
            # results, so the model always sees the songs it needs to add.
            entry["tracks"] = library.album_tracks(entry)
            entry["track_count"] = len(entry["tracks"])
        return json.dumps(albums)
    return json.dumps(
        library.search_tracks(artist=artist, title=title, album=album, limit=5))


@tool
def music_information(artist: str, title: str = "", album: str = ""):
    """Look up what Last.fm knows about one record: how many people listen to
    it (`listeners`), how often it is played (`playcount`), the tags listeners
    give it (`tags` — the closest thing to a genre), a short description
    (`summary`), a cover image URL (`image`), and for an album its tracklist.
    Read-only; nothing is added or changed.

    Pass `artist` plus EITHER `title` (for a song) or `album` (for a release).
    Use it for "what genre is this", "how popular is it", "what's on this
    album", or to tell an original apart from a cover or a soundalike before
    wishlisting it — none of that is in the wishlist or in MusicBrainz results.

    Returns a JSON object, or a plain sentence when Last.fm has no API key
    configured or nothing on the record. Both are real answers: report them as
    they are and never substitute listener counts, tags, or a description from
    your own memory.
    """
    if not lastfm.available():
        return ("No Last.fm API key is configured, so listener counts, tags "
                "and descriptions are unavailable. The user can add a key in "
                "Settings or as LASTFM_API_KEY.")
    if not (title or album):
        return "Pass a title (for a song) or an album (for a release)."
    try:
        info = (lastfm.track_info(artist, title) if title
                else lastfm.album_info(artist, album))
    except lastfm.LastfmError as error:
        return f"The Last.fm lookup failed: {error}"
    if not info:
        return (f"Last.fm has nothing on {title or album} by {artist} — the "
                "spelling may differ, or it may not be indexed.")
    return json.dumps(info)


@tool
def artist_top_albums(artist: str, limit: int = 10):
    """List an artist's best-known releases, most-played first — Last.fm's
    nearest thing to a discography. Read-only; nothing is added.

    Use it for "what albums has X put out", "what should I get by X", or to
    find an album's exact name before calling search_music(kind="album").

    Returns a JSON list, most popular first:
        {source, mb_id, album, artist, year, rank, playcount, url, image}

    Two things this CANNOT tell you, because Last.fm publishes neither:
    - `year` is always null and there are no release dates anywhere in this
      result, so it can NOT identify an artist's newest or latest release. If
      the user asks what is new, say that this ranks by popularity and that you
      cannot date these — never fill a year in from your own memory.
    - `rank` orders by playcount, so a recent release sits low simply because
      fewer people have played it yet. A low rank does not mean old or obscure.

    No tracklists come back here — this is a browsing tool. To wishlist
    anything from the list, call search_music(kind="album") with the album name
    and add its `tracks`. `mb_id` is the MusicBrainz RELEASE id, which is NOT
    what a wishlist item stores, so never pass it to add_wishlist_item; it is
    often empty, which is normal.

    Answers in plain text when no Last.fm key is configured or the artist is
    unknown — report that as the answer instead of supplying albums yourself.
    """
    if not lastfm.available():
        return ("No Last.fm API key is configured, so artist discographies are "
                "unavailable. The user can add a key in Settings or as "
                "LASTFM_API_KEY.")
    if not artist.strip():
        return "Pass an artist name."
    try:
        albums = lastfm.artist_top_albums(
            artist, limit=min(max(limit, 1), _MAX_ALBUMS))
    except lastfm.LastfmError as error:
        return f"The Last.fm lookup failed: {error}"
    if not albums:
        return (f"Last.fm lists no albums for {artist} — the spelling may "
                "differ, or the artist may not be indexed. Try "
                "correct_artist_name.")
    # Drop the fields this endpoint never populates: an empty tracklist here
    # would read to the model as "this release has no songs".
    return json.dumps([
        {field: album[field] for field in
         ("source", "mb_id", "album", "artist", "year", "rank", "playcount",
          "url", "image")}
        for album in albums])


@tool
def correct_artist_name(artist: str):
    """Resolve a possibly-misspelled artist name to the spelling Last.fm files
    them under ("Guns and Roses" -> "Guns N' Roses"). Read-only.

    Use it when search_music or artist_top_albums came back empty, or before
    adding an item whose artist the user typed by ear — a wishlist row filed
    under a misspelling will not match the collection when reconcile_wishlist
    later checks whether they own it.

    Returns JSON: {source, artist, mb_id, url, corrected}. `corrected` is true
    only when the canonical name actually differs from what you passed; false
    means the spelling was already right, which is a useful answer too. `mb_id`
    is the artist's MusicBrainz id where Last.fm has one and is often empty —
    that is normal, and it is an ARTIST id, so never store it on a wishlist
    item, whose mb_id is a recording id.

    Answers in plain text when no key is configured or Last.fm has no such
    artist at all. Retry the original search with the corrected name before
    telling the user nothing was found.
    """
    if not lastfm.available():
        return ("No Last.fm API key is configured, so artist name corrections "
                "are unavailable. The user can add a key in Settings or as "
                "LASTFM_API_KEY.")
    if not artist.strip():
        return "Pass an artist name."
    try:
        match = lastfm.artist_correction(artist)
    except lastfm.LastfmError as error:
        # Last.fm reports an unknown artist as an error body — an answer about
        # the name, not a broken lookup.
        if "could not be found" in str(error).lower():
            return (f"Last.fm has no artist matching {artist!r}, and so no "
                    "correction for it. The name may be misspelled beyond what "
                    "its corrections database covers, or simply not indexed.")
        return f"The Last.fm lookup failed: {error}"
    if not match:
        return (f"Last.fm has no correction on file for {artist!r}; use the "
                "name as the user gave it.")
    return json.dumps(match)


@tool
def reconcile_wishlist():
    """Auto-detect which wishlist items the user now owns and mark them
    acquired.

    Scans the wishlist against the music collection; any not-yet-acquired item
    that matches a track the user owns (by MusicBrainz id, else by
    artist+title) has its status set to "acquired" and is linked to the
    collection track via `acquired_id`. Read-only against the collection and
    idempotent — already-acquired items are skipped, and it never adds,
    removes, or edits anything else. Use it when the user asks whether they
    already own something on their wishlist, or to refresh acquired status.

    Returns how many items were newly marked acquired and their ids.
    """
    updated = library.reconcile_wishlist(_wl())
    if not updated:
        return "No new acquisitions detected — nothing on the wishlist matched the collection."
    return json.dumps({
        "newly_acquired": len(updated),
        "items": updated,
    })


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
def remove_wishlist_items(item_ids: list[int]):
    """Remove SEVERAL items from the user's wishlist at once, by their ids.

    Use this for any multi-item removal instead of calling
    `remove_wishlist_item` in a loop — it shows the user ONE confirmation
    dialog listing every item and deletes them in a single database
    transaction, which is far faster and avoids the lock contention a
    one-at-a-time loop causes. Only touches the wishlist; it never affects the
    music library or files on disk. Calling this tool automatically shows the
    confirmation dialog, so do NOT ask for permission in chat first. Verify the
    ids first (via `list_wishlist`/`search_wishlist`); to empty the whole
    wishlist use `clear_wishlist` instead.

    Returns a JSON object with how many items were removed and the artist/title
    of each — relay those exact values.
    """
    ids = [int(i) for i in item_ids]
    removed = [item for item in (_wl().get_item(i) for i in ids) if item]
    count = _wl().remove_items(ids)
    return json.dumps({
        "removed": count,
        "items": [{"id": item["id"],
                   "artist": item.get("artist", ""),
                   "title": item.get("title", "")}
                  for item in removed],
    })


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
