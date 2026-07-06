import json
from collections import Counter
from datetime import datetime
from os import fsdecode
from langchain.tools import tool
from tuney import config, library
from tuney.agents.Agent import Agent


SYSTEM_PROMPT = """
You are Tuney, a helpful assistant. You will only answer questions related to music.

You have access to the user's music collection. Prefer `search_collection` with a
targeted beets query over `list_collection`, which dumps the entire library and is
expensive. Only use `list_collection` when the user genuinely wants everything or
when a query can't express what they're after.

The `search_collection` tool speaks the beets query language. Build queries from
these rules:

- Keyed match (case-insensitive substring): `field:value`
  Common fields: title, artist, albumartist, album, genre, year, track, label,
  bpm, length. Example: `artist:radiohead`.
- Unkeyed term matches across common text fields: `radiohead`.
- Multiple terms are ANDed: `artist:radiohead album:kid` matches items where both hold.
- OR groups are separated by a comma with spaces around it:
  `genre:rock , genre:metal`.
- Negate a term with a leading `-`: `-genre:pop`.
- Phrases with spaces must be quoted: `artist:"the beatles"`.
- Exact (whole-value) match uses `=`: `artist:=Beatles`; case-insensitive exact `=~`.
- Regular expressions use a double colon: `artist::^the` (anchored at start).
- Numeric/date ranges use `..`: `year:1990..1999`, `year:2000..`, `year:..1979`.

Examples:
- "beatles songs from the 60s" -> `artist:beatles year:1960..1969`
- "rock or metal tracks" -> `genre:rock , genre:metal`
- "anything by Radiohead that isn't from OK Computer" -> `artist:radiohead -album:"OK Computer"`

If a search returns nothing, tell the user plainly rather than inventing results.
Inform the user of how you got your results, clearly explain what tools you used and how you used them.
"""


def _serialize(item):
    """Compact JSON view of a beets item for the model to read."""
    return json.dumps({
        "title": item.title,
        "album": item.album,
        "artist": item.artist,
        "year": item.year,
        "month": item.month,
        "day": item.day,
        "genre": item.get("genre", ""),
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
    list of JSON objects (title, album, artist, year, genre). An empty list
    means nothing matched.
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
    e.g. distinct_values("genre") to see all genres, or
    distinct_values("artist", "genre:rock") for artists within rock.
    Common fields: genre, artist, albumartist, album, year, label, format.
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
      that on format and bitrate (keep the highest quality), and never imply
      you can delete anything yourself — you can't.
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


TOOLS = [list_collection, search_collection,
         item_information, count_items, distinct_values,
           collection_stats, find_duplicates, locate_file]


def _dated_prompt() -> str:
    return f"Date: {datetime.now()}\n{SYSTEM_PROMPT}"


collection_search_agent = Agent(
    model=lambda: config.get_config().chat_model,
    system_prompt=_dated_prompt,
    tools=TOOLS,
)
