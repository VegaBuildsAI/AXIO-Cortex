@echo off
cd /d C:\Users\AXIO\axio-console
echo Installing required packages...
python -m pip install "httpx[socks]" anthropic --break-system-packages -q
echo.
echo Running AXIO Assessment...
python engine/assess.py
echo.
echo Done! Press any key to close.
pause
