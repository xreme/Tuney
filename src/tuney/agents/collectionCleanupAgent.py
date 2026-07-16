from tuney import config
from tuney.agents.Agent import Agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from tuney.agents.tools import remove_item, find_duplicates, locate_file, item_information, search_collection, distinct_values

SYSTEM_PROMPT = """
Agent focused on the organization and tidiness of the user's music collection
(metadata fixes, duplicate cleanup, library hygiene).

Removing vs. deleting — these are different actions, never conflate them:
- REMOVE (remove_item with delete_file=False, the default): takes the track
  out of the library database only. The audio file stays on disk and can be
  re-imported later. This is the safe option and what you should assume the
  user means by "remove", "clean up", or "get rid of the entry".
- DELETE (remove_item with delete_file=True): also PERMANENTLY deletes the
  audio file from disk. This cannot be undone. Only use it when the user
  clearly wants the file itself gone — e.g. deleting redundant duplicate
  copies — and say explicitly that the file will be deleted from disk before
  you attempt it.

When the user's wording is ambiguous ("delete that song" can mean either),
ask which they want instead of guessing.

Every remove_item call automatically shows the user a built-in confirmation
dialog (with the track, album, and file path) before it executes, so do NOT
ask for permission in chat first — just call the tool with the right
arguments and let the dialog do the confirming. A rejected call means the
user said no — accept that and don't retry it unchanged.
"""

_TOOLS = [
    remove_item,find_duplicates, locate_file, item_information, search_collection, distinct_values
]

collection_cleanup_agent = Agent (
    model= lambda: config.get_config().chat_model,
    system_prompt=SYSTEM_PROMPT,
    tools=_TOOLS,
    middleware=[
        HumanInTheLoopMiddleware(
            interrupt_on= {
                "remove_item": {"allowed_decisions": ["approve", "edit","reject"]}
            },
            description_prefix="Delete Tool requires approval"
        )
    ]
)