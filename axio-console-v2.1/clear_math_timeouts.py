"""
clear_math_timeouts.py — removes stale timeout error entries from
axio-console-v2.1/logs/model_tests.jsonl so health flags clear.

Removes entries where "error" key is present (timeout/exception) for:
  - MATH-001 (all models — now handled by python_exact route)
  - ARCH-001 / qwen3:14b only (stale — qwen3:14b no longer on ARCH route)

Safe to run multiple times. Scored entries and clean runs are untouched.
"""
import json
import shutil
import datetime
from pathlib import Path

LOG = Path(__file__).parent / "logs" / "model_tests.jsonl"

if not LOG.exists():
    print(f"[ERROR] Not found: {LOG}")
    raise SystemExit(1)

# Backup
bak = LOG.with_suffix(f".bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
shutil.copy2(LOG, bak)
print(f"[OK] Backup → {bak.name}")

entries = []
with open(LOG, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            entries.append(json.loads(line))

kept    = []
removed = 0
for e in entries:
    stale = False
    # MATH-001 timeouts — all models, replaced by python_exact route
    if e.get("test_id") == "MATH-001" and "error" in e:
        stale = True
    # ARCH-001 timeout for qwen3:14b — stale, qwen3:14b no longer on ARCH route
    if e.get("test_id") == "ARCH-001" and e.get("model") == "qwen3:14b" and "error" in e:
        stale = True

    if stale:
        print(f"  Removing stale timeout: {e.get('model')} / {e.get('test_id')}  ({e.get('error', '')[:60]})")
        removed += 1
    else:
        kept.append(e)

with open(LOG, "w", encoding="utf-8") as f:
    for e in kept:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

print(f"\n[OK] Removed {removed} stale timeout entries. {len(kept)} entries remain.")
print(f"[OK] Saved → {LOG}")
