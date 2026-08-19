"""Run the Tuney assistant once from the terminal, without opening the TUI.

The answer goes to stdout so it can be piped or redirected; progress and tool
activity go to stderr, and confirmations are asked on the terminal.
"""

import asyncio
import sys

import typer

# The supervisor's delegation tools, in the user's terms — the same wording the
# chat pane uses.
_TOOL_LABELS = {
    "collection_search": "Searching your collection",
    "collection_cleanup": "Working on your library",
    "wishlist": "Working on your wishlist",
}


def _note(text: str) -> None:
    """Progress goes to stderr, keeping stdout to just the answer."""
    print(text, file=sys.stderr, flush=True)


def _describe(request: dict) -> str:
    if request.get("description"):
        return request["description"]
    args = request.get("args") or {}
    detail = ", ".join(f"{name}={value!r}" for name, value in args.items())
    name = request.get("name") or "action"
    return f"{name}({detail})" if detail else name


async def _decide(requests: list, approve_all: bool) -> list[dict]:
    """One decision per request, in order.

    Without a terminal to ask on, everything is declined: a piped or scripted
    one-shot run must never silently retag, convert or delete files.
    """
    decisions = []
    for request in requests:
        description = _describe(request)
        if approve_all:
            _note(f"  [approved] {description}")
            decisions.append({"type": "approve"})
        elif not sys.stdin.isatty():
            _note(f"  [declined] {description}")
            decisions.append({
                "type": "reject",
                "message": "Declined: this ran non-interactively. "
                           "Re-run with --yes, or use the TUI.",
            })
        elif typer.confirm(f"\nTuney wants to: {description}\nAllow?"):
            decisions.append({"type": "approve"})
        else:
            decisions.append({"type": "reject",
                              "message": "The user declined this action."})
    return decisions


async def _render(events, quiet: bool) -> list | None:
    """Print the assistant's reply as it streams, returning any action
    requests the run paused on."""
    pending = None
    async for kind, token in events:
        if kind == "text":
            sys.stdout.write(token)
            sys.stdout.flush()
        elif kind == "tool" and not quiet:
            name = token.get("name", "")
            _note(f"  · {_TOOL_LABELS.get(name, name or 'working')}")
        elif kind == "interrupt":
            pending = token
    return pending


async def _run(prompt: str, approve_all: bool, quiet: bool) -> None:
    from tuney.agents import confirmation
    from tuney.agents.supervisor import tuney_agent

    # Specialists nested inside a delegation ask through this handler rather
    # than surfacing as a graph interrupt.
    confirmation.set_confirmation_handler(
        lambda requests: _decide(requests, approve_all))
    try:
        pending = await _render(tuney_agent.astream(prompt), quiet)
        while pending:
            decisions = await _decide(pending, approve_all)
            pending = await _render(tuney_agent.aresume(decisions), quiet)
    finally:
        confirmation.set_confirmation_handler(None)


def ask(prompt: str, approve_all: bool = False, quiet: bool = False) -> None:
    """Ask the assistant one question and print the answer. Raises typer.Exit
    with a non-zero status when the run fails."""
    from tuney.agents.Agent import error_detail

    try:
        asyncio.run(_run(prompt, approve_all, quiet))
    except KeyboardInterrupt:
        _note("\nInterrupted.")
        raise typer.Exit(code=130)
    except RuntimeError as e:
        if "No API key" in str(e):
            _note("No OpenRouter API key set. Add one under Settings in the "
                  "TUI, or set OPENROUTER_API_KEY.")
            raise typer.Exit(code=1)
        _note(f"\nError: {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        _note(f"\nError: {error_detail(e)}")
        raise typer.Exit(code=1)
    print()
