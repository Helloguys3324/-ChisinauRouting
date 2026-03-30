@echo off
title Chisinau Routing Engine
color 0A
chcp 65001 >nul 2>&1

REM ============================================================
REM CHISINAU ROUTING ENGINE - ONE-CLICK LAUNCHER
REM ============================================================
REM Double-click this file to start everything!
REM Press Ctrl+C or close the window to stop all services.
REM ============================================================

set PGROOT=D:\PostgreSQL\pgsql
set PGDATA=D:\PostgreSQL\data
set PGBIN=%PGROOT%\bin
set VENV=D:\ChisinauRouting\ingestion\venv
set PROJECT=D:\ChisinauRouting\ingestion

REM Add PostgreSQL to PATH
set PATH=%PGBIN%;%PATH%

echo.
echo ============================================================
echo     CHISINAU ROUTING ENGINE - STARTING...
echo ============================================================
echo.

REM Check if PostgreSQL is already running
"%PGBIN%\pg_ctl.exe" status -D "%PGDATA%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] PostgreSQL is already running
    echo Verifying connection...
    timeout /t 1 /nobreak >nul
) else (
    echo Starting PostgreSQL...
    "%PGBIN%\pg_ctl.exe" start -D "%PGDATA%" -l "D:\PostgreSQL\postgresql.log" -w
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to start PostgreSQL!
        echo Check D:\PostgreSQL\postgresql.log for details.
        pause
        exit /b 1
    )
    echo [OK] PostgreSQL started
    echo Waiting for database to be ready...
    timeout /t 3 /nobreak >nul
)
echo.

REM Verify database connection
echo Verifying database connection...
"%PGBIN%\psql.exe" -U chisinau -d chisinau_routing -c "SELECT 1;" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Database connection failed, waiting 3 more seconds...
    timeout /t 3 /nobreak >nul
    "%PGBIN%\psql.exe" -U chisinau -d chisinau_routing -c "SELECT 1;" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [WARNING] Still cannot connect, trying one more time...
        timeout /t 3 /nobreak >nul
        "%PGBIN%\psql.exe" -U chisinau -d chisinau_routing -c "SELECT 1;" >nul 2>&1
        if %ERRORLEVEL% NEQ 0 (
            echo [ERROR] Cannot connect to database after multiple attempts!
            echo.
            echo Troubleshooting:
            echo 1. Check if PostgreSQL is running: %PGBIN%\pg_ctl.exe status -D %PGDATA%
            echo 2. Check log file: D:\PostgreSQL\postgresql.log
            echo 3. Try manual start: D:\PostgreSQL\start_postgres.bat
            echo.
            pause
            exit /b 1
        )
    )
)
echo [OK] Database connection verified
echo.

REM Run the dashboard (this will start all workers)
echo Starting Dashboard and Workers...
echo.
call "%VENV%\Scripts\activate.bat"
cd /d "%PROJECT%"
python dashboard.py

REM When dashboard exits (Ctrl+C), cleanup
echo.
echo ============================================================
echo     SHUTTING DOWN...
echo ============================================================
echo.

REM Ask if should stop PostgreSQL
choice /C YN /M "Stop PostgreSQL server as well"
if %ERRORLEVEL% EQU 1 (
    echo Stopping PostgreSQL...
    "%PGBIN%\pg_ctl.exe" stop -D "%PGDATA%"
    echo [OK] PostgreSQL stopped
) else (
    echo PostgreSQL left running
)

echo.
echo ============================================================
echo     ALL SERVICES STOPPED
echo ============================================================
echo.
pause
