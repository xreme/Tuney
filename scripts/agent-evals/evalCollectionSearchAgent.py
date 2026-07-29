import asyncio
import time
from tuney.agents.Agent import Agent
from tuney.agents.collectionSearchAgent import TOOLS, _dated_prompt
from langchain.messages import HumanMessage, AIMessage, ToolMessage
from agentevals.trajectory.match import create_trajectory_match_evaluator

def build(model: str) -> Agent:
    return Agent(model=model, system_prompt=_dated_prompt, tools=TOOLS)

candidate_models = ["google/gemini-2.5-flash",
                    "qwen/qwen3.7-flash",
                    "deepseek/deepseek-v4-flash",
                    ]


async def test_models():
    for candidate in candidate_models:
        agent = build(candidate)

        start = time.perf_counter()
        response = await agent.ainvoke("How many Amine songs do I have?")
        elapsed = time.perf_counter() - start

        print(f"{candidate}")
        print(f"Time: {elapsed:.2f}s")
        print(response)
        print("-" * 80)

asyncio.run(test_models())
