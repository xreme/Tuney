"""OpenRouter rate card, for estimating cost from token counts.

Companion to the exact per-call cost OpenRouter reports back when a request
asks for it: this estimates instead, from the public price list, which is what
lets you re-cost an old results CSV or project what a given case would cost at
volume without spending anything.

"""

import json
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

MODELS_URL = "https://openrouter.ai/api/v1/models"  # public, no auth needed
CACHE_PATH = Path(__file__).parent / "openrouter-rates.json"
MAX_AGE_S = 7 * 24 * 60 * 60


def _price(value) -> float | None:
    """Parse a pricing field. OpenRouter sends per-token USD as strings, and
    uses negative values for models with no fixed price (e.g. auto-routing)."""
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price >= 0 else None


def fetch_rates() -> dict:
    with urllib.request.urlopen(MODELS_URL, timeout=30) as resp:
        payload = json.load(resp)

    rates = {}
    for model in payload.get("data", []):
        pricing = model.get("pricing") or {}
        rates[model["id"]] = {
            "prompt": _price(pricing.get("prompt")),
            "completion": _price(pricing.get("completion")),
            # Fixed per-request fee, charged on top of tokens by some models.
            "request": _price(pricing.get("request")) or 0.0,
        }
    return {"fetched_at": time.time(), "rates": rates}


@lru_cache(maxsize=1)
def load_rates(refresh: bool = False) -> dict:
    """Rate card by model id, from a local cache refreshed weekly.

    Falls back to a stale cache if the fetch fails, so a network blip during a
    benchmark run costs you accuracy rather than the whole run.
    """
    cached = None
    if CACHE_PATH.exists():
        cached = json.loads(CACHE_PATH.read_text())
        fresh = time.time() - cached.get("fetched_at", 0) < MAX_AGE_S
        if fresh and not refresh:
            return cached["rates"]

    try:
        card = fetch_rates()
    except Exception as e:
        if cached is None:
            print(f"  ! rate card unavailable ({type(e).__name__}: {e})")
            return {}
        print(f"  ! rate card refresh failed ({type(e).__name__}), using cache")
        return cached["rates"]

    CACHE_PATH.write_text(json.dumps(card, indent=2))
    return card["rates"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimated USD for one run, or None if the model isn't priced per token.

    Reasoning tokens are already counted in output_tokens by OpenRouter, so
    they must not be added again here.
    """
    rate = load_rates().get(model)
    if not rate or rate["prompt"] is None or rate["completion"] is None:
        return None
    return (
        input_tokens * rate["prompt"]
        + output_tokens * rate["completion"]
        + rate["request"]
    )


def rate_summary(model: str) -> str:
    """Per-million-token rates, for showing what an estimate was based on."""
    rate = load_rates().get(model)
    if not rate or rate["prompt"] is None or rate["completion"] is None:
        return "unpriced"
    return f"${rate['prompt'] * 1e6:.2f}/M in, ${rate['completion'] * 1e6:.2f}/M out"
