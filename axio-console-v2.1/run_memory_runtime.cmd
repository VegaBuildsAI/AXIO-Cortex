@echo off
REM AXIO memory runtime launcher for Task Scheduler.
REM cd to the project dir so .env loads (Cortex on 127.0.0.1:5432). Args pass through.
cd /d "%~dp0"
set AXIO_MEMORY_BACKEND=postgres
".venv\Scripts\python.exe" scripts\axio_memory_runtime.py %*
