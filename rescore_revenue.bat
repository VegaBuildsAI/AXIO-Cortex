@echo off
echo ============================================================
echo  Re-scoring revenue benchmarks with fixed rubric (v2)
echo ============================================================
echo.

echo [1/2] Clearing old revenue scores from main project...
python "C:\Users\AXIO\AXIO Model Improvement\clear_revenue_scores.py"
echo.

echo [2/2] Running assessment with updated rubric (main project)...
cd /d C:\Users\AXIO\axio-console
python engine\assess.py
echo.
echo ============================================================
echo  Done. Check axio-console\engine\assessments.jsonl for latest ASSESS.
echo ============================================================
pause
