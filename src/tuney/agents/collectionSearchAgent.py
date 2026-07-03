from langchain.agents import create_agent
# from deepagents import create_deep_agent
from langchain_openrouter import ChatOpenRouter
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessageChunk
from tuney import library
from tuney.credentials import get_api_key
import json
from datetime import datetime

MODEL = "moonshotai/kimi-k2.5"

SYSTEM_PROMPT = f"""

Date: {datetime.now()}

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


_agent = None


def _get_agent():
    global _agent
    if _agent is not None:
        return _agent

    key = get_api_key()
    if not key:
        raise RuntimeError("No API key provided")

    model = ChatOpenRouter(
        model=MODEL,
        openrouter_api_key=key,
    )

    _agent = create_agent(
        model = model,
        tools=[list_collection, search_collection],
        system_prompt= SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )

    return _agent

def query_search_agent(message: str, thread_id: str = "default") -> str:
    result = _get_agent().invoke(
        {
            "messages": [{
                "role":"user",
                "content": message
            }]
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    return result["messages"][-1].content_blocks[-1]['text']


async def aquery_search_agent(message: str, thread_id: str = "default") -> str:
    result = await _get_agent().ainvoke(
        {
            "messages": [{
                "role":"user",
                "content": message
            }]
        },
        config={"configurable": {"thread_id": thread_id}},
    )

    return result["messages"][-1].content_blocks[-1]['text']

async def astream_search_agent(message: str, thread_id: str = "default"):
    """Yield the assistant's answer text token-by-token.

    Skips reasoning and tool-call chunks; only the visible answer text is
    streamed. The generator finishes when the agent is done responding.
    """
    async for chunk, _meta in _get_agent().astream(
        {
            "messages": [{
                "role":"user",
                "content": message
            }]
        },
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="messages",
    ):
        if isinstance(chunk, AIMessageChunk):
            for block in chunk.content_blocks:
                if block.get("type") == "text" and block.get("text"):
                    yield block["text"]
