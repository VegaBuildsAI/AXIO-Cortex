# AXIO Model Improvement — Change Log
Generated: 2026-05-09 | Based on ASSESS-002

---

## Summary

Three files created here replace their originals in `engine/rubrics/` and `config/`.
**No original files were modified.** To apply, copy these files over the originals.

---

## Fix 1 — REVREC Rubric Mismatch (Critical)

**File:** `engine/rubrics/revenue.md`

**Problem:** All models scored 0-5 on REVREC-001. Root cause: the benchmark
prompt asks for an *ASC 606 decision tree for identifying performance obligations*,
but the rubric scored *contract extraction and revenue allocation schedules* —
a completely different task. The judge had no valid basis for scoring.

**Fix:** Rubric rewritten to match the actual prompt:
- Scores the two-part distinctness test (capable + separately identifiable)
- Rewards correct SaaS obligation types (license, implementation, support, training)
- Requires decision-tree structure (Yes/No branches), not just bullet lists
- Grades ASC 606 five-step coverage and edge cases

**Expected impact:** Models like qwen3:8b (which produced well-structured trees)
should score 60-80 on re-run. The 0s were false negatives.

---

## Fix 2 — Route qwen3:14b out of Primary Slots (High)

**File:** `config/routing.yaml`

**Problem:** qwen3:14b was assigned to `revenue_analysis` (max_context: 16384)
but timed out on 2/4 benchmark tasks (MATH-001, ARCH-001) even at 600s.
ASSESS-002 health flags confirmed repeated timeout_errors.

**Fix:**
- `revenue_analysis` → `qwen3-coder:30b` (completed all 4 tasks, avg ~54)
- All `max_context` values halved to reduce VRAM pressure and timeout risk
- `premium_reasoning` gets a local fallback chain (`qwen3-coder:30b`) for when
  the Claude API is unavailable
- `qwen3:14b` retained in the fallback chain for premium_reasoning only

---

## Fix 3 — Model Role Corrections (Medium)

**File:** `config/models.yaml`

| Model | Old Role | New Role | Reason |
|---|---|---|---|
| qwen3:14b | reasoning_medium | fallback_reasoning | Timeout on 50% of benchmarks |
| qwen3-coder:30b | coding_agent | coding_and_analysis | Reliable across all task types |
| llama3.1:8b | fallback_fast | fallback_fast (caution added) | Avg score 34 — weakest performer |

Benchmark averages added to each model entry for visibility.

---

## Next Recommended Actions

1. **Copy these files over originals** to activate the fixes
2. **Re-run REVREC benchmarks** with the corrected rubric:
   `python scripts/benchmark_models.py` (all models, revenue test only)
3. **Re-run ASSESS-003** to confirm revenue scores improve and timeout flags clear
4. **Consider adding a math tool call** for exact arithmetic — all models failed MATH-001
   because they tried to compute 8-digit multiplication in their heads
