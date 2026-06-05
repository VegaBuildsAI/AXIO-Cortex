"""
Clears revenue benchmark scores from model_tests.jsonl so they get
re-scored by the updated rubric on the next assess.py run.
"""
import json
from pathlib import Path

MODEL_TESTS = Path("C:/Users/AXIO/axio-console/logs/model_tests.jsonl")
# v2.1 log (also cleared if it exists, but v2.1 already has the correct rubric scores)
# MODEL_TESTS = Path(__file__).parent / "axio-console-v2.1" / "logs" / "model_tests.jsonl"

entries = []
with open(MODEL_TESTS, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            entries.append(json.loads(line))

cleared = 0
for e in entries:
    if e.get("test_type") == "revenue" and e.get("score") is not None:
        print(f"  Clearing: {e['model']} / {e['test_id']}  (was score={e['score']}, label={e.get('score_label')})")
        e.pop("score", None)
        e.pop("score_label", None)
        e.pop("score_reasoning", None)
        e.pop("scored_at", None)
        e.pop("scored_by", None)
        cleared += 1

with open(MODEL_TESTS, "w", encoding="utf-8") as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"\nDone. {cleared} revenue entries cleared and ready for re-scoring.")
