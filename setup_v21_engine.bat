@echo off
setlocal enabledelayedexpansion

set V21=C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1
set MAIN=C:\Users\AXIO\axio-console
set IMPROVE=C:\Users\AXIO\AXIO Model Improvement

echo ============================================================
echo  AXIO v2.1 — Self-Contained Engine Setup + Assessment
echo ============================================================
echo.

:: ── Step 1: Copy engine from main project into v2.1 ───────────
echo [1/6] Installing engine/ into v2.1...
if not exist "%V21%\engine" mkdir "%V21%\engine"
if not exist "%V21%\engine\rubrics" mkdir "%V21%\engine\rubrics"
if not exist "%V21%\logs" mkdir "%V21%\logs"

xcopy /E /I /H /Y "%MAIN%\engine\*.py"      "%V21%\engine\" >nul
xcopy /E /I /H /Y "%MAIN%\engine\rubrics\*" "%V21%\engine\rubrics\" >nul
echo   engine/ copied from main project.

:: ── Step 2: Apply fixed revenue rubric immediately ────────────
echo [2/6] Applying fixed revenue rubric...
copy /Y "%IMPROVE%\engine\rubrics\revenue.md" "%V21%\engine\rubrics\revenue.md" >nul
echo   revenue.md (v2) applied — decision tree scoring.

:: ── Step 3: Copy .env so scorer can reach Claude API ──────────
echo [3/6] Copying .env for API key access...
if exist "%MAIN%\.env" (
    copy /Y "%MAIN%\.env" "%V21%\.env" >nul
    echo   .env copied.
) else (
    echo   WARNING: No .env found in main project.
)

:: ── Step 4: Copy benchmark results if v2.1 has no logs ────────
echo [4/6] Checking for v2.1 logs...
if not exist "%V21%\logs\model_tests.jsonl" (
    echo   No model_tests.jsonl found in v2.1.
    echo   Copying benchmark results from main project as baseline.
    xcopy /E /I /H /Y "%MAIN%\logs\*" "%V21%\logs\" >nul
    echo   Logs copied. These reflect the same Ollama models.
) else (
    echo   v2.1 has its own logs — using those.
)

echo.

:: ── Step 5: Run assessment from within v2.1 ───────────────────
echo [5/6] Running assessment scoped to v2.1...
cd /d "%V21%"
python engine/assess.py
echo.

:: ── Step 6: Apply all remaining fix files ─────────────────────
echo [6/6] Applying config fixes...
copy /Y "%IMPROVE%\config\routing.yaml" "%V21%\config\routing.yaml" >nul
echo   routing.yaml applied (qwen3-coder:30b on revenue_analysis)
copy /Y "%IMPROVE%\config\models.yaml"  "%V21%\config\models.yaml" >nul
echo   models.yaml  applied (corrected roles + benchmark avgs)
copy /Y "%IMPROVE%\CHANGES.md"          "%V21%\CHANGES.md" >nul
echo   CHANGES.md   copied

echo.
echo ============================================================
echo  v2.1 is now self-contained with its own engine + fixes.
echo  Assessments will save to:
echo    %V21%\engine\assessments.jsonl
echo ============================================================
echo.
pause
