from tuney import config
from tuney.agents.Agent import Agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

from tuney.agents.tools import remove_item, find_duplicates, locate_file, item_information, search_collection, distinct_values

SYSTEM_PROMPT = """
Agent focused on the organization and ordiness of the user's collection
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