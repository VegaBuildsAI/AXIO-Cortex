@echo off
echo ============================================================
echo  AXIO v2.1 — Full Benchmark Run (clean baseline)
echo  Routes: math=Python, revenue=qwen3:14b, coding=qwen3-coder:30b
echo ============================================================
echo.

cd /d "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"

echo [1/3] Running all benchmarks against all models...
echo   MATH-001  → python_exact  (no Ollama)
echo   CODING-001 → qwen3-coder:30b, qwen3:8b, llama3.1:8b
echo   REVREC-001 → qwen3:14b, qwen3:8b, llama3.1:8b
echo   ARCH-001   → qwen3-coder:30b, qwen3:8b, llama3.1:8b
echo.
echo   NOTE: This will take 10-20 minutes depending on model load.
echo.
python scripts\benchmark_models.py
echo.

echo [2/3] Scoring any unscored responses...
echo   (assess.py will call scorer automatically)
echo.

echo [3/3] Running assessment to capture new baseline...
python engine\assess.py
echo.

echo ============================================================
echo  Full benchmark complete.
echo  Check engine/assessments.jsonl for the latest ASSESS.
echo ============================================================
pause
