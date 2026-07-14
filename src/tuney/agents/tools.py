from langchain.tools import tool
from tuney import library
import json
from collections import Counter
from os import fsdecode


def _serialize(item):
    """Compact JSON view of a beets item for the model to read."""
    return json.dumps({
        "title": item.title,
        "album": item.album,
        "artist": item.artist,
        "year": item.year,
        "month": item.month,
        "day": item.day,
        "genres": item.get("genre", ""),
        "beets_id": item.id,
    })

@tool
def list_collection():
    """Return the user's entire music collection as a list of JSON items.

    Expensive on large libraries — prefer `search_collection` when the user is
    looking for something specific.
    """
    return [_serialize(item) for item in library.all_items()]


@tool
def search_collection(query: str):
    """Search the user's music collection using a beets query string.

    Pass a beets query built from the query language described in the system
    prompt (e.g. `artist:radiohead year:2000..`). Returns matching items as a
    list of JSON objects (title, album, artist, year, genres). An empty list
    means nothing matched.

    Matching is literal (substring), so spacing and spelling matter:
    `artist:speakerknockerz` will not match "Speaker Knockerz". On an empty
    result, retry with variations before concluding the item is missing —
    change the spacing, use a spacing-tolerant regex like
    `artist::(?i)speaker.?knockerz`, try a shorter fragment, or correct the
    spelling — as described in the system prompt.
    """
    return [_serialize(item) for item in library.search(query)]

@tool
def count_items(query: str) -> str:
    """
    Count the matches of a given query against the user's music collection using a beets query.

    Pass a beets query built from the query language described in the system
    prompt (e.g. `artist:radiohead year:2000..`). Returns the count of matched items.
    """

    return len(library.search(query))

@tool
def distinct_values(field: str, query: str = ""):
    """List every unique value of a field in the collection, with track counts.

    Use this to discover what's actually in the library before searching —
    e.g. distinct_values("genres") to see all genres, or
    distinct_values("artist", "genres:rock") for artists within rock.
    Common fields: genres, artist, albumartist, album, year, label, format.
    The optional query uses the same beets query language as search_collection.
    Returns a JSON object mapping each value to how many tracks have it,
    most common first.
    """
    items = library.search(query) if query else library.all_items()
    counts = Counter(str(item.get(field, "")) for item in items)
    counts.pop("", None)   # tracks missing the field entirely
    counts.pop("0", None)  # beets stores missing numeric fields (year) as 0
    return json.dumps(dict(counts.most_common()))

@tool
def collection_stats():
    """Summary statistics for the whole library: track, album, and artist
    counts, total playtime, and the year range.

    Cheap — prefer this over list_collection for "tell me about my
    collection" style questions.
    """
    items = library.all_items()
    artists = {item.artist for item in items if item.artist}
    albums = {(item.albumartist or item.artist, item.album)
              for item in items if item.album}
    years = [item.year for item in items if item.year]
    total_seconds = int(sum(item.length or 0 for item in items))
    hours, minutes = divmod(total_seconds // 60, 60)[::-1] if False else (total_seconds // 3600, (total_seconds % 3600) // 60)

    return json.dumps({
        "tracks": len(items),
        "albums": len(albums),
        "artists": len(artists),
        "total_playtime": f"{hours}h {minutes}m",
        "earliest_year": min(years) if years else None,
        "latest_year": max(years) if years else None,
    })

@tool
def item_information(itemId: int):
    """
    Retrieve full information about a specific item in the User's internal library DB by beets_id.
    Useful for fetching item specific information.
    Ex: '42'
    """
    item = library.get_item(itemId)
    if item is None:
        return f"No item found with the beets_id {itemId}"
    item_json = {
        k: (fsdecode(v) if isinstance(v, bytes) else v)
        for k, v in dict(item).items()
    }

    return json.dumps(item_json)

@tool
def locate_file(itemId: int):
    """
    Return the absolute path of a track's audio file on disk, looked up by beets_id.

    Find the beets_id with `search_collection` first. Use this when the user asks
    where a track is stored or wants to open the file itself.
    Reports if the item doesn't exist, its drive isn't mounted right now, or
    its file is missing from disk.
    """
    try:
        path = library.locate_file(itemId)
    except library.DriveNotMounted as missing:
        return (
            f"The file was at {missing.args[0]} when it was imported, but the "
            "drive it lives on isn't mounted right now, so the file can't be "
            "accessed. Reconnect the drive to use it."
        )
    except FileNotFoundError as missing:
        return f"The library entry points to {missing.args[0]}, but no file exists there anymore."
    if path is None:
        return f"No item found with the beets_id {itemId}"
    return path

@tool
def find_duplicates():
    """Find songs that exist more than once in the user's collection, grouped
    by matching artist + title.

    Returns a list of groups; each group lists every copy of one song with its
    album, year, format, bitrate, and beets_id. An empty list means no
    duplicates. Scans the whole library — no query needed.

    Interpret each group before reporting; do not present the raw groups:
    - Copies on the SAME album are true file duplicates (the actionable kind).
    - Copies on DIFFERENT albums are usually intentional: deluxe/expanded
      editions, compilations, or singles. Treat albums as editions of the same
      release when one album name extends the other (e.g. "Glockaveli" and
      "Glockaveli: The Don"). Summarize edition overlap at the album level
      ("all 18 tracks of X also appear on Y") instead of listing every track,
      and do not call these duplicates.
    - Only recommend which copy to remove if the user explicitly asks; base
      that on format and bitrate (keep the highest quality). Removal itself
      goes through `remove_item`, which requires explicit per-track user
      confirmation first.
    """
    groups = library.duplicates()
    return json.dumps([
        [{
            "title": it.title, "artist": it.artist, "album": it.album,
            "year": it.year, "format": it.format, "bitrate": it.bitrate,
            "file_location": fsdecode(it.path), "beets_id": it.id,
        } for it in group]
        for group in groups
    ])

@tool
def scan_directory(dir: str):
    """Scan a directory to import its music into the user's collection.

    Pass an absolute path. Runs a beets import of everything under that
    directory and updates the user's library DB. This is a long-running
    operation — on a large directory it may take a very long time.
    Returns the tail of the import log so you can tell the user what happened.
    """
    if not dir.is_dir():
        return "This path is not a directory on this disk"

    library.scan(dir)

@tool
def remove_item(item_id: int, delete_file: bool = False):
    """Remove a track from the user's library, looked up by beets_id.

    With delete_file=False (the default) only the library DB entry is removed;
    the audio file stays on disk. With delete_file=True the audio file is
    PERMANENTLY deleted from disk as well — this cannot be undone.

    This tool acts immediately, with no confirmation step of its own. Before
    calling it you MUST:
    - Have the user's explicit go-ahead for this specific track in this
      conversation. Never remove anything speculatively or as part of a batch
      the user hasn't seen.
    - Confirm the target: call `item_information` with the beets_id and echo
      the title/artist/album back to the user, so a wrong or stale id can't
      delete the wrong file.
    - Only pass delete_file=True if the user clearly wants the file itself
      gone (e.g. deleting a duplicate copy), not just removed from the
      library.

    Returns a message confirming what was removed, or an error if the id
    doesn't exist.
    """
    item = library.get_item(item_id)
    if item is None:
        return f"No item found with id: {item_id}"
    library.remove_item(item, delete=delete_file)
    what = "library entry and audio file" if delete_file else "library entry (file kept on disk)"
    return f"Removed {what}: {item.artist} - {item.title} ({item.album})"