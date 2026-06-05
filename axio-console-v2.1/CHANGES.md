# AXIO Model Improvement — Change Log
Generated: 2026-05-09 | Last updated: ASSESS-006

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

---

## Fix 4 — Benchmark-Informed Route Correction (ASSESS-006, 2026-05-09)

**Files:** `config/routing.yaml`, `config/models.yaml`

**Problem:** After re-scoring revenue with the corrected REVREC-001 rubric, benchmark
data showed qwen3:14b is clearly the better revenue model (85/Good) vs qwen3-coder:30b
(72/Good). The previous routing fix (Fix 2) had moved revenue to qwen3-coder:30b due
to timeout concerns — but those timeouts were on MATH and ARCH, not revenue tasks.

**Fix:**
- `revenue_analysis` route restored to `qwen3:14b` (scored 85 on REVREC-001)
- `qwen3-coder:30b` returned to `coding_agent` only — revenue removed from its role
- `premium_reasoning` fallback chain updated: qwen3-coder:30b → qwen3:14b
  (qwen3:14b is the stronger reasoning model for business/financial logic)
- `models.yaml` roles corrected: qwen3:14b → reasoning_medium, qwen3-coder:30b → coding_agent
- `not_recommended_for: revenue analysis` added to qwen3-coder:30b to prevent future drift

**Final benchmark summary (ASSESS-006):**

| Model | Coding | Architecture | Revenue | Math |
|---|---|---|---|---|
| qwen3:14b | 92 | — | **85** | timeout |
| qwen3:8b | 92 | 82 | 72 | timeout |
| qwen3-coder:30b | **92** | 75 | 72 | 0 |
| llama3.1:8b | 72 | 45 | 35 | 15 |

---

## Health Flags (ASSESS-006)

| Severity | Model | Issue | Root Cause |
|---|---|---|---|
| WARN | qwen3:8b | 1 benchmark timeout | MATH-001: attempted 8-digit multiplication inline; exceeded 600s |
| WARN | qwen3:14b | 2 benchmark timeouts | MATH-001 + ARCH-001: both exceeded 600s at 8192 context |

**Recommended fix for both flags:** Add a Python tool call for `exact_math` route.
All models timed out or scored 0 on MATH-001 because they tried to compute large
multiplication in-context. Routing math to a Python interpreter would clear both flags.

---

## Next Recommended Actions

1. ✅ REVREC rubric corrected (Fix 1)
2. ✅ Timeout-causing routes capped (Fix 2)
3. ✅ Model roles corrected (Fix 3)
4. ✅ Revenue route restored to qwen3:14b based on benchmark data (Fix 4)
5. **Add Python math tool** to clear the 2 remaining timeout health flags (MATH-001)
6. **Run fresh benchmarks** now that routing is correct — MATH-001 with python tool,
   ARCH-001 with qwen3:14b at lower context to test if timeout clears
