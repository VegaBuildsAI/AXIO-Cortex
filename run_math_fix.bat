@echo off
echo ============================================================
echo  AXIO v2.1 — Wire exact_math route and clear health flags
echo ============================================================
echo.

cd /d "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"

echo [1/3] Clearing stale timeout entries (MATH-001 all models + ARCH-001 qwen3:14b)...
python clear_math_timeouts.py
echo.

echo [2/3] Running MATH-001 via Python exact_math tool...
python scripts\benchmark_models.py --test MATH-001
echo.

echo [3/3] Running full assessment (health flags should clear)...
python engine\assess.py
echo.

echo ============================================================
echo  Done. Math route is now wired to Python tool.
echo  Check engine/assessments.jsonl for latest ASSESS.
echo ============================================================
pause
