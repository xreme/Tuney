import json
from datetime import datetime
from os import fsdecode
from langchain.tools import tool
from tuney import library
from tuney.agents.Agent import Agent

MODEL = "moonshotai/kimi-k2.5"

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


TOOLS = [list_collection, search_collection, item_information]


def _dated_prompt() -> str:
    return f"Date: {datetime.now()}\n{SYSTEM_PROMPT}"


collection_search_agent = Agent(
    model=MODEL,
    system_prompt=_dated_prompt,
    tools=TOOLS,
)
