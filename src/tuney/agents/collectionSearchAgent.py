from langchain.agents import create_agent
# from deepagents import create_deep_agent
from langchain_openrouter import ChatOpenRouter
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from tuney import library
from tuney.credentials import get_api_key

MODEL = "moonshotai/kimi-k2.5"

SYSTEM_PROMPT = """
You are Tuney, a helpful assistant. You will only answer questions related to music.
"""

@tool
def list_collection():
    """Get the user's collection"""
    return  library.all_items()


def _get_agent():
    key = get_api_key()
    if not key:
        raise RuntimeError("No API key provided")

    model = ChatOpenRouter(
        model=MODEL,
        openrouter_api_key=key,
    )

    agent = create_agent(
        model = model,
        tools=[list_collection],
        system_prompt= SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )

    return agent

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