import asyncio
import csv
import time
from datetime import datetime
from pathlib import Path
from collectionCases import CASES
from tuney.agents.Agent import Agent
from tuney.agents.collectionSearchAgent import TOOLS, _dated_prompt
from agentevals.trajectory.match import create_trajectory_match_evaluator

def build(model: str) -> Agent:
    return Agent(model=model, system_prompt=_dated_prompt, tools=TOOLS)

RESULTS_DIR = Path(__file__).parent / "results"

candidate_models = ["google/gemini-2.5-flash",
                    "openai/gpt-oss-120b",
                    "qwen/qwen3.7-flash",
                    "deepseek/deepseek-v4-flash",
                    ]

async def run_case(agent, prompt):
    agent.new_thread()

    start = time.perf_counter()
    state = await agent.arun(prompt)
    elapsed = time.perf_counter() - start

    ai = [m for m in state["messages"] if m.type == "ai"]
    usage = [m.usage_metadata for m in ai if getattr(m, "usage_metadata", None)]
    reasoning = [
        b["reasoning"]
        for m in ai
        for b in m.content_blocks
        if b.get("type") == "reasoning" and b.get("reasoning")
    ]
    return {
        "state": state,
        "answer": state["messages"][-1].text,
        "elapsed_s": elapsed,
        "input_tokens": sum(u["input_tokens"] for u in usage),
        "output_tokens": sum(u["output_tokens"] for u in usage),
        "reasoning_tokens": sum(
            (u.get("output_token_details") or {}).get("reasoning", 0) for u in usage
        ),
        "reasoning_traces": reasoning,
        "llm_calls": len(ai),
        "tool_calls": [tc["name"] for m in ai for tc in (m.tool_calls or [])],
    }

async def evaluate(model: str, case: dict) -> dict:
    row = {"model": model, "case": case["name"]}
    try:
        result = await run_case(build(model), case["prompt"])
    except Exception as e:
        return row | {"error": f"{type(e).__name__}: {e}"}

    evaluator = create_trajectory_match_evaluator(
        trajectory_match_mode="superset",
        tool_args_match_mode="ignore",
        tool_args_match_overrides=case["arg_matchers"],
    )
    score = evaluator(outputs=result["state"], reference_outputs=case["reference"])

    return row | {
        "trajectory_ok": score["score"],
        "elapsed_s": result["elapsed_s"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "reasoning_tokens": result["reasoning_tokens"],
        "llm_calls": result["llm_calls"],
        "tool_calls": result["tool_calls"],
        "answer": result["answer"],
    }

async def test_models():
    for candidate in candidate_models:
        try:
            agent = build(candidate)

            start = time.perf_counter()
            response = await agent.ainvoke("How many Amine songs do I have?")
            elapsed = time.perf_counter() - start

            print(f"{candidate}")
            print(f"Time: {elapsed:.2f}s")
            print(response)
            print("-" * 40)
        except Exception as e:
            print(f"FAILED: {candidate}")
            print(type(e).__name__)
            print(e)


CSV_COLUMNS = [
    "model",
    "case",
    "trajectory_ok",
    "elapsed_s",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "llm_calls",
    "tool_calls",
    "answer",
    "error",
]

def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, restval="")
        writer.writeheader()
        for row in rows:
            out = {k: v for k, v in row.items() if k in CSV_COLUMNS}
            if "tool_calls" in out:
                out["tool_calls"] = "; ".join(out["tool_calls"])
            if "elapsed_s" in out:
                out["elapsed_s"] = f"{out['elapsed_s']:.2f}"
            writer.writerow(out)

async def main() -> None:
    rows = []
    for model in candidate_models:
        for case in CASES:
            row = await evaluate(model, case)
            rows.append(row)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = RESULTS_DIR / f"collection-search-agent-{stamp}.csv"
    write_csv(rows, path)
    print(f"\nwrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    asyncio.run(main())
