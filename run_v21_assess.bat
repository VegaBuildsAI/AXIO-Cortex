@echo off
setlocal enabledelayedexpansion

set SRC=C:\Users\AXIO\axio-console-v2.1
set DEST=C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1
set MAIN=C:\Users\AXIO\axio-console
set IMPROVE=C:\Users\AXIO\AXIO Model Improvement

echo ============================================================
echo  AXIO v2.1 — Copy, Assess, and Fix
echo ============================================================
echo.

:: ── Step 1: Copy v2.1 into AXIO Model Improvement ─────────────
echo [1/5] Copying axio-console-v2.1 into AXIO Model Improvement...
if exist "%DEST%" (
    echo   Destination already exists — skipping copy.
) else (
    xcopy /E /I /H /Y "%SRC%" "%DEST%" >nul
    if errorlevel 1 (
        echo   ERROR: Copy failed. Check that %SRC% exists.
        pause
        exit /b 1
    )
    echo   Copied successfully.
)
echo.

:: ── Step 2: Install required packages ─────────────────────────
echo [2/5] Installing required Python packages...
python -m pip install anthropic "httpx[socks]" --break-system-packages -q
echo   Done.
echo.

:: ── Step 3: Run assessment ─────────────────────────────────────
echo [3/5] Running assessment...
if exist "%DEST%\engine\assess.py" (
    echo   Found engine/assess.py in v2.1 — running it directly.
    cd /d "%DEST%"
    python engine/assess.py
) else (
    echo   No engine/ in v2.1 — running assessment from main project.
    cd /d "%MAIN%"
    python engine/assess.py
)
echo.

:: ── Step 4: Apply fixed files ──────────────────────────────────
echo [4/5] Applying improved rubric, routing, and models config...

if not exist "%DEST%\engine\rubrics" mkdir "%DEST%\engine\rubrics"
if not exist "%DEST%\config" mkdir "%DEST%\config"

copy /Y "%IMPROVE%\engine\rubrics\revenue.md"  "%DEST%\engine\rubrics\revenue.md" >nul
echo   revenue.md   applied

copy /Y "%IMPROVE%\config\routing.yaml"        "%DEST%\config\routing.yaml" >nul
echo   routing.yaml applied

copy /Y "%IMPROVE%\config\models.yaml"         "%DEST%\config\models.yaml" >nul
echo   models.yaml  applied

copy /Y "%IMPROVE%\CHANGES.md"                 "%DEST%\CHANGES.md" >nul
echo   CHANGES.md   copied
echo.

:: ── Step 5: Report ─────────────────────────────────────────────
echo [5/5] Done. Summary:
echo   Source        : %SRC%
echo   Destination   : %DEST%
echo   Fixes applied : revenue.md, routing.yaml, models.yaml, CHANGES.md
echo.
echo ============================================================
echo  All steps complete.
echo  Check: C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\
echo ============================================================
echo.
pause
