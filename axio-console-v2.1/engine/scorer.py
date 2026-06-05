"""
AXIO Improvement Engine — Scorer
Claude-as-judge evaluator for benchmark responses.

Reads unscored entries from logs/model_tests.jsonl,
calls Claude to grade each response using the matching rubric,
and writes scores back into model_tests.jsonl in place.
"""

import json
import os
import subprocess as _subprocess
import sys
from pathlib import Path
from datetime import datetime


def _ensure_pkg(pip_name: str, import_name: str = None):
    """Auto-install a package if it isn't importable yet."""
    import importlib
    mod = import_name or pip_name.split("[")[0]
    try:
        importlib.import_module(mod)
    except ImportError:
        print(f"[scorer] Auto-installing missing package: {pip_name}")
        _subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name,
             "--break-system-packages", "-q"],
            check=False,
        )


_ensure_pkg("anthropic")
_ensure_pkg("httpx[socks]", "socksio")   # needed when SOCKS proxy is active

try:
    import anthropic
except ImportError:
    print("[scorer] ERROR: anthropic package not installed. Run: pip install anthropic")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# ── Paths ──────────────────────────────────────────────────────────────────────
ENGINE_DIR   = Path(__file__).parent
RUBRICS_DIR  = ENGINE_DIR / "rubrics"
LOGS_DIR     = ENGINE_DIR.parent / "logs"
MODEL_TESTS  = LOGS_DIR / "model_tests.jsonl"

RUBRIC_MAP = {
    "math":         RUBRICS_DIR / "math.md",
    "coding":       RUBRICS_DIR / "coding.md",
    "architecture": RUBRICS_DIR / "architecture.md",
    "revenue":      RUBRICS_DIR / "revenue.md",
}

JUDGE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


def load_rubric(test_type: str) -> str:
    path = RUBRIC_MAP.get(test_type)
    if not path or not path.exists():
        return f"Score this response on a scale of 0-100. Return JSON: {{\"score\": <int>, \"label\": \"<label>\", \"reasoning\": \"<text>\"}}"
    return path.read_text(encoding="utf-8")


def score_response(client: anthropic.Anthropic, entry: dict) -> dict:
    """
    Score a single benchmark entry. Returns the entry with score, label,
    score_reasoning, and scored_at fields added.
    """
    test_type = entry.get("test_type", "unknown")
    model     = entry.get("model", "unknown")
    response  = entry.get("response", "")
    rubric    = load_rubric(test_type)

    prompt = f"""You are an expert evaluator for AI model benchmarks.

Below is a rubric followed by a model response to evaluate.

---RUBRIC---
{rubric}

---MODEL RESPONSE (from {model})---
{response[:6000]}
---END---

Score the response strictly according to the rubric. Return ONLY a valid JSON object with no extra text:
{{"score": <0-100>, "label": "<Excellent|Good|Partial|Weak|Fail>", "reasoning": "<2-3 sentences>"}}"""

    try:
        message = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)
        entry["score"]           = result.get("score")
        entry["score_label"]     = result.get("label")
        entry["score_reasoning"] = result.get("reasoning")
        entry["scored_at"]       = datetime.now().isoformat()
        entry["scored_by"]       = JUDGE_MODEL
        print(f"  [scorer] {model} / {test_type}: {result.get('score')}/100 — {result.get('label')}")

    except json.JSONDecodeError as e:
        print(f"  [scorer] Parse error for {model}/{test_type}: {e}")
        entry["score_error"] = f"parse_error: {e}"
    except anthropic.APIError as e:
        print(f"  [scorer] API error for {model}/{test_type}: {e}")
        entry["score_error"] = f"api_error: {e}"

    return entry


def run_scorer(verbose: bool = True) -> list[dict]:
    """
    Main entry point. Reads model_tests.jsonl, scores all unscored entries
    that have a valid response, writes results back, and returns the full
    updated list of entries.
    """
    if not MODEL_TESTS.exists():
        print("[scorer] model_tests.jsonl not found — nothing to score.")
        return []

    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        print("[scorer] WARNING: No ANTHROPIC_API_KEY found. Skipping scoring.")
        return _load_entries()

    client = anthropic.Anthropic(api_key=api_key)

    entries = _load_entries()
    to_score = [
        e for e in entries
        if e.get("score") is None
        and e.get("response")
        and not e.get("error")
        and not e.get("score_error")
    ]

    if not to_score:
        if verbose:
            print("[scorer] All scorable entries already scored.")
        return entries

    if verbose:
        print(f"[scorer] Scoring {len(to_score)} unscored entries...")

    scored_map = {_entry_key(e): e for e in entries}
    for entry in to_score:
        updated = score_response(client, entry)
        scored_map[_entry_key(updated)] = updated

    all_entries = list(scored_map.values())
    _write_entries(all_entries)

    scored_count = sum(1 for e in to_score if e.get("score") is not None)
    if verbose:
        print(f"[scorer] Done. {scored_count}/{len(to_score)} entries scored successfully.")

    return all_entries


def _entry_key(entry: dict) -> str:
    return f"{entry.get('model')}|{entry.get('test_id')}"


def _load_entries() -> list[dict]:
    entries = []
    with open(MODEL_TESTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def _write_entries(entries: list[dict]) -> None:
    with open(MODEL_TESTS, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    results = run_scorer(verbose=True)
    scored = [e for e in results if e.get("score") is not None]
    print(f"\nSummary: {len(scored)}/{len(results)} entries have scores.")
