@echo off
REM AXIO memory startup — invoked by the current-user scheduled task at logon.
REM Ensures the Cortex Postgres is up and the canonical knowledge is synced into it.
set AXIO_MEMORY_BACKEND=postgres

REM Wait for Docker Desktop to finish starting after logon (best-effort).
timeout /t 60 /nobreak >nul

REM Bring up the Cortex container (idempotent; restart:unless-stopped usually already did).
pushd "C:\Users\AXIO\AXIO Model Improvement"
docker compose up -d >nul 2>&1
popd

REM Give Postgres a moment to accept connections, then reconcile + sync knowledge.
timeout /t 8 /nobreak >nul
cd /d "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
".venv\Scripts\python.exe" scripts\migrate_ioaf_resilience.py >> "%TEMP%\axio_memory_startup.log" 2>&1
".venv\Scripts\python.exe" scripts\axio_memory_runtime.py --once --sync-only >> "%TEMP%\axio_memory_startup.log" 2>&1
".venv\Scripts\python.exe" scripts\mirror_postgres_to_chroma.py >> "%TEMP%\axio_memory_startup.log" 2>&1
