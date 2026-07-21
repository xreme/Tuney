from datetime import datetime

from langchain.tools import tool

from tuney import config
from tuney.agents import activity
from tuney.agents.Agent import Agent
from tuney.agents.confirmation import confirm
from tuney.agents.collectionSearchAgent import collection_search_agent
from tuney.agents.collectionCleanupAgent import collection_cleanup_agent


async def _delegate(specialist: Agent, task: str, name: str = "specialist") -> str:
    """Run a task on a specialist and return its final answer text.

    If the specialist pauses for tool confirmation, ask the active UI via the
    confirmation bridge and resume it with the user's decisions, repeating
    until the specialist finishes.
    """
    # Every task is a self-contained brief, so the specialist needs no memory
    # of earlier delegations — and a fresh thread keeps one oversized run
    # (e.g. a huge search result) from blowing the context of every later one.
    specialist.new_thread()

    parts: list[str] = []
    pending: list | None = None

    async def _consume(events) -> None:
        nonlocal pending
        pending = None
        async for kind, token in events:
            if kind == "interrupt":
                pending = token
            elif kind == "text":
                parts.append(token)

    token = activity.start(name, task)
    try:
        await _consume(specialist.astream(task))
        while pending:
            decisions = await confirm(pending)
            await _consume(specialist.aresume(decisions))
    finally:
        activity.finish(token)
    return "".join(parts) or "(the specialist returned no answer)"


@tool
async def collection_search(task: str) -> str:
    """Ask the collection search specialist about the user's music library.

    Use for anything read-only: finding tracks/albums/artists, counting or
    listing items, library statistics, distinct genres/artists, locating a
    track's file on disk, or checking whether something is in the collection.

    Write `task` as a self-contained brief with every name, spelling, id, and
    constraint the specialist needs — it cannot see the chat.
    """
    return await _delegate(collection_search_agent, task, name="Search")


@tool
async def collection_cleanup(task: str) -> str:
    """Ask the cleanup specialist to tidy the user's music library.

    Use for anything that changes the library: removing tracks or albums,
    finding and clearing duplicates, fixing or repairing metadata (the
    specialist can re-run the autotagger against MusicBrainz to correct
    tags — "retag", "fix the tags", "repair the metadata"), and general
    library hygiene. The specialist shows the user a built-in confirmation
    dialog before any removal or retag, so delegate without asking
    permission in chat first.

    Write `task` as a self-contained brief with every name, spelling, id, and
    constraint the specialist needs — it cannot see the chat. The user's verb
    carries meaning the specialist acts on, so preserve it exactly: "delete"
    means erase the files from disk, "remove" means take them out of the
    library only. If the user used neither, don't substitute one — pass their
    wording through and let the specialist ask.

    For metadata fixes, delegate the WHOLE job as one task ("fix the tags of
    the track with beets id NNN; likely artist/title: ...") — never split
    candidate lookup and application across separate delegations. The
    specialist has no memory between tasks, and MusicBrainz recording ids
    must never be retyped or invented — not by you, not in a brief. The
    specialist re-derives ids itself and its built-in dialog collects the
    user's approval, so one delegation covers the entire fix.
    """
    return await _delegate(collection_cleanup_agent, task, name="Cleanup")


# Reply-length guidance per chat detail level; the user switches levels in
# settings or with a hotkey in the chat screen.
_DETAIL_GUIDANCE = {
    config.ChatDetail.HIGH: (
        "The user has chosen HIGH detail: show lots of information — full "
        "lists, relevant metadata, and context around the answer — and you "
        "are allowed to be more verbose when it genuinely adds value."
    ),
    config.ChatDetail.NORMAL: (
        "The user has chosen NORMAL detail: keep replies brief — the "
        "essentials plus a little useful extra. This is a small terminal "
        "window, so a couple of sentences (or a tight list when the user "
        "asked for items) is the right size."
    ),
    config.ChatDetail.LOW: (
        "The user has chosen LOW detail: essentials only. Give the shortest "
        "accurate answer — a sentence or a bare list — and leave out "
        "everything optional."
    ),
}

SYSTEM_PROMPT = """
You are Tuney, a helpful assistant. You will only answer questions related to
music. You have a witty and mildly sarcastic personality, pretty sassy.

{detail_guidance}

Lead with the answer, add jokes and quips, and no recaps of what you did, no
explaining which tools or specialists you used, you can have offers of
follow-up help.

You don't touch the user's music library yourself — two specialists do the
real work, and you delegate to them through your tools:

- collection_search — read-only questions: finding music, getting random tracks, counts, stats,
  what's in the collection, where files live.
- collection_cleanup — changes: removing tracks or albums, duplicate cleanup,
  library hygiene.

How to delegate:
- Each task must be a self-contained brief. The specialists don't see this
  conversation, so restate names, ids, spellings, and constraints every time
  ("remove the 3 duplicate copies of 'Creep' by Radiohead, keeping the one
  from Pablo Honey; library removal only, don't delete files").
- A request can need both specialists — e.g. search first to identify items,
  then cleanup to act on them.
- Relay what a specialist reports faithfully in your own voice — never invent
  tracks, counts, or outcomes — but keep the mechanics (tools, queries,
  retries) to yourself; the user just wants the answer.
- Removals trigger a built-in confirmation dialog shown directly to the user,
  so don't ask permission in chat first. If the specialist reports the user
  declined, accept it and don't retry the same action.
- "delete" vs "remove" is a real distinction (disk vs library-only) — quote
  the user's verb in cleanup briefs, and if the specialist comes back asking
  which one the user meant, put that question to the user.
- If a specialist comes back empty-handed or confused, refine the brief and
  try again before telling the user it can't be done.

Make sure to make jokes and poke fun a the user. be charasmatic. 

Make sure you have structured outputs, use tables whenever possible
"""


def _dated_prompt() -> str:
    # Day granularity: the agent rebuilds when its prompt string changes, so
    # anything finer would force a rebuild on every message.
    prompt = SYSTEM_PROMPT.format(
        detail_guidance=_DETAIL_GUIDANCE[config.get_config().chat_detail]
    )
    return f"Date: {datetime.now():%A %d %B %Y}\n{prompt}"


tuney_agent = Agent(
    # Pinned per docs/model-benchmark.md; ignores the chat_model setting until
    # per-role model config exists.
    model="google/gemini-3-flash-preview",
    system_prompt=_dated_prompt,
    tools=[collection_search, collection_cleanup],
)
