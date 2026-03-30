@echo off
REM Simple dashboard test without workers
title Chisinau Routing - Dashboard Only
color 0A

set VENV=D:\ChisinauRouting\ingestion\venv
set PROJECT=D:\ChisinauRouting\ingestion
set PGBIN=D:\PostgreSQL\pgsql\bin
set PATH=%PGBIN%;%PATH%

echo.
echo Starting Dashboard (without workers for testing)...
echo.

call "%VENV%\Scripts\activate.bat"
cd /d "%PROJECT%"

REM Run simple dashboard
python simple_dashboard.py

pause
