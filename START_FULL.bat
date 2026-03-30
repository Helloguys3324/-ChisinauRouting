@echo off
REM ==================================================
REM  CHISINAU ROUTING ENGINE - FULL SYSTEM LAUNCHER
REM ==================================================
REM  Starts: PostgreSQL + GTFS-RT Worker + TomTom Worker + Dashboard
REM ==================================================

title Chisinau Routing Engine - Full System
color 0A

set VENV=D:\ChisinauRouting\ingestion\venv
set PROJECT=D:\ChisinauRouting\ingestion
set PGBIN=D:\PostgreSQL\pgsql\bin
set PGDATA=D:\PostgreSQL\data
set PATH=%PGBIN%;%PATH%

echo.
echo ======================================================================
echo   CHISINAU ROUTING ENGINE - SYSTEM STARTUP
echo ======================================================================
echo.

REM ===== Step 1: Check PostgreSQL =====
echo [1/4] Checking PostgreSQL status...
"%PGBIN%\pg_ctl.exe" -D "%PGDATA%" status >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo   PostgreSQL is not running. Starting...
    "%PGBIN%\pg_ctl.exe" -D "%PGDATA%" -l "D:\PostgreSQL\postgresql.log" start
    timeout /t 5 /nobreak >nul
    
    REM Verify PostgreSQL started
    "%PGBIN%\psql.exe" -U postgres -d postgres -c "SELECT 1" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   [ERROR] Failed to start PostgreSQL!
        echo   Check log: D:\PostgreSQL\postgresql.log
        pause
        exit /b 1
    )
    echo   [OK] PostgreSQL started successfully
) else (
    echo   [OK] PostgreSQL is already running
)

echo.
REM ===== Step 2: Clean up old connections =====
echo [2/4] Cleaning up old idle connections...
"%PGBIN%\psql.exe" -U postgres -d chisinau_routing -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'chisinau_routing' AND state = 'idle' AND application_name = '';" >nul 2>&1
echo   [OK] Cleanup complete

echo.
REM ===== Step 3: Activate Python environment =====
echo [3/4] Activating Python environment...
call "%VENV%\Scripts\activate.bat"
cd /d "%PROJECT%"
echo   [OK] Environment ready

echo.
REM ===== Step 4: Launch dashboard with workers =====
echo [4/4] Starting dashboard and workers...
echo.
echo ======================================================================
echo   System starting...
echo   - Database: localhost:5432/chisinau_routing
echo   - GTFS-RT Worker: Polling Roataway API every 30s
echo   - TomTom Worker: Polling Traffic API every 10 min
echo   - Dashboard: Updating every 5 seconds
echo ======================================================================
echo.
echo   Press Ctrl+C to stop all components
echo.

REM Start the dashboard (which will start workers as subprocesses)
python dashboard.py

REM Cleanup on exit
echo.
echo.
echo ======================================================================
echo   Shutting down...
echo ======================================================================
echo.

REM Workers are already stopped by dashboard.py signal handler

echo   [OK] System stopped
echo.
pause
