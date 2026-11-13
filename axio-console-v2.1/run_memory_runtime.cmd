@echo off
REM AXIO memory runtime launcher for Task Scheduler.
REM The scheduled tasks start this through `conhost.exe --headless`, so no
REM window opens; output is appended to logs\memory_runtime_task.log instead.
REM cd to the project dir so .env loads (Cortex on 127.0.0.1:5433). Args pass through.
cd /d "%~dp0"
set AXIO_MEMORY_BACKEND=postgres
if not exist "%~dp0logs" mkdir "%~dp0logs"
echo [%date% %time%] axio_memory_runtime.py %* >> "%~dp0logs\memory_runtime_task.log"
".venv\Scripts\python.exe" scripts\axio_memory_runtime.py %* >> "%~dp0logs\memory_runtime_task.log" 2>&1
exit /b %ERRORLEVEL%
