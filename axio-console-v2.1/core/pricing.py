"""
AXIO Core -- Token usage + estimated cost for Claude turns.

Prices are USD per 1M tokens (input, output), from the Anthropic pricing table.
Cache reads bill at ~0.1x input; cache writes at ~1.25x input (5-min TTL).
Update PRICING if Anthropic changes rates.
"""

# model-id prefix -> (input $/MTok, output $/MTok)
PRICING = {
    "claude-opus-5":     (5.0, 25.0),
    "claude-opus-4-8":   (5.0, 25.0),
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-opus-4-6":   (5.0, 25.0),
    "claude-sonnet-5":   (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}

CACHE_READ_MULT  = 0.1     # cached-prefix reads
CACHE_WRITE_MULT = 1.25    # cache creation (5-min TTL)


def _rates(model):
    for prefix, rates in PRICING.items():
        if model and model.startswith(prefix):
            return rates
    return None


def _g(usage, key):
    """Read a token field from an SDK Usage object or a plain dict.

    Returns an int; anything non-numeric (None, Mock, str) coerces to 0 so the
    counter never crashes on an incomplete/mocked usage object.
    """
    if usage is None:
        return 0
    value = usage.get(key, 0) if isinstance(usage, dict) else getattr(usage, key, 0)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def tokens(usage):
    """Normalize any usage into a dict of the four token counts."""
    return {
        "input":       _g(usage, "input_tokens"),
        "output":      _g(usage, "output_tokens"),
        "cache_read":  _g(usage, "cache_read_input_tokens"),
        "cache_write": _g(usage, "cache_creation_input_tokens"),
    }


def cost_usd(model, usage):
    """Estimated USD for one turn. None if the model has no known price."""
    rates = _rates(model)
    if not rates:
        return None
    t = usage if isinstance(usage, dict) and "input" in usage else tokens(usage)
    in_rate, out_rate = rates
    total = (
        t["input"] * in_rate
        + t["cache_read"] * in_rate * CACHE_READ_MULT
        + t["cache_write"] * in_rate * CACHE_WRITE_MULT
        + t["output"] * out_rate
    ) / 1_000_000.0
    return total


def add(acc, usage):
    """Accumulate a usage into a running dict (for multi-step agent loops)."""
    t = tokens(usage)
    for k, v in t.items():
        acc[k] = acc.get(k, 0) + v
    return acc


def summarize(model, usage):
    """Compact one-line summary: tokens + estimated cost."""
    t = usage if isinstance(usage, dict) and "input" in usage else tokens(usage)
    cost = cost_usd(model, t)
    cache = ""
    if t["cache_read"] or t["cache_write"]:
        cache = f" · cache {t['cache_read']:,}r/{t['cache_write']:,}w"
    cost_str = f"~${cost:.4f}" if cost is not None else "n/a"
    return (f"tokens: in {t['input']:,}{cache} · out {t['output']:,} "
            f"· {cost_str} ({model})")
