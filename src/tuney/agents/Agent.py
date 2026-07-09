import asyncio
import uuid
from collections.abc import Callable, Sequence

from langchain.agents import create_agent
from langchain.tools import BaseTool
from langchain_core.messages import AIMessageChunk
from langchain_openrouter import ChatOpenRouter
from langgraph.checkpoint.memory import InMemorySaver

from tuney.credentials import get_api_key

_REQUEST_TIMEOUT_MS = 60_000

_STREAM_INACTIVITY_TIMEOUT = 120.0


class Agent:
    """A conversational agent configured with a model, system prompt, and tools.

    Each instance owns its own conversation thread. The underlying langgraph
    agent is built lazily on first use, so configured instances can be created
    at import time without an API key.
    """

    def __init__(
        self,
        *,
        model: str | Callable[[], str],
        system_prompt: str | Callable[[], str],
        tools: Sequence[BaseTool] = (),
        thread_id: str | None = None,
    ):
        self._model = model
        self._system_prompt = system_prompt
        self._tools = list(tools)
        self._thread_id = thread_id or str(uuid.uuid4())
        self._agent = None

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        key = get_api_key()
        if not key:
            raise RuntimeError("No API key provided")

        prompt = self._system_prompt
        if callable(prompt):
            prompt = prompt()

        model = self._model
        if callable(model):
            model = model()

        self._agent = create_agent(
            model=ChatOpenRouter(
                model=model,
                openrouter_api_key=key,
                timeout=_REQUEST_TIMEOUT_MS,
            ),
            tools=self._tools,
            system_prompt=prompt,
            checkpointer=InMemorySaver(),
        )
        return self._agent

    def _payload(self, message: str) -> dict:
        return {"messages": [{"role": "user", "content": message}]}

    def _config(self) -> dict:
        return {"configurable": {"thread_id": self._thread_id}}

    async def ainvoke(self, message: str) -> str:
        """Send a message and return the assistant's full answer text."""
        result = await self._get_agent().ainvoke(
            self._payload(message),
            config=self._config(),
        )
        return result["messages"][-1].content_blocks[-1]["text"]

    async def astream(self, message: str):
        """Yield ("reasoning" | "text", token) pairs as the assistant responds. """
        stream = aiter(self._get_agent().astream(
            self._payload(message),
            config=self._config(),
            stream_mode="messages",
        ))
        while True:
            try:
                chunk, _meta = await asyncio.wait_for(
                    anext(stream), timeout=_STREAM_INACTIVITY_TIMEOUT
                )
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise RuntimeError(
                    "The AI service stopped responding "
                    f"(no data for {_STREAM_INACTIVITY_TIMEOUT:.0f}s). "
                    "Check your connection and try again."
                ) from None
            if isinstance(chunk, AIMessageChunk):
                for block in chunk.content_blocks:
                    if block.get("type") == "text" and block.get("text"):
                        yield "text", block["text"]
                    elif block.get("type") == "reasoning" and block.get("reasoning"):
                        yield "reasoning", block["reasoning"]
