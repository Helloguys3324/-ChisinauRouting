@echo off
REM ==================================================
REM  CHISINAU TRANSPORT - WEB MAP APPLICATION
REM ==================================================
REM  Beautiful 3D map with real-time trolleybus tracking
REM ==================================================

chcp 65001 >nul
title Chisinau Transport - 3D Map
color 0A

set VENV=D:\ChisinauRouting\ingestion\venv
set WEBAPP=D:\ChisinauRouting\webapp
set PGBIN=D:\PostgreSQL\pgsql\bin
set PGDATA=D:\PostgreSQL\data

echo.
echo ======================================================================
echo   CHISINAU TRANSPORT - 3D MAP APPLICATION
echo ======================================================================
echo.

REM Check if port 5000 is already in use
netstat -ano | findstr :5000 | findstr LISTENING >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [!] Port 5000 already in use!
    echo   [!] Server might be already running.
    echo   [!] Use STOP_MAP.bat to stop it first.
    echo.
    pause
    exit /b
)

REM Check PostgreSQL
echo [1/3] Checking PostgreSQL...
"%PGBIN%\pg_ctl.exe" -D "%PGDATA%" status >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   Starting PostgreSQL...
    "%PGBIN%\pg_ctl.exe" -D "%PGDATA%" -l "D:\PostgreSQL\postgresql.log" start
    timeout /t 3 /nobreak >nul
)
echo   [OK] PostgreSQL running
echo.

REM Activate Python environment
echo [2/3] Activating Python environment...
call "%VENV%\Scripts\activate.bat"
echo   [OK] Environment ready
echo.

REM Start web server
echo [3/3] Starting web server...
echo.
echo ======================================================================
echo   SERVER STARTED!
echo ======================================================================
echo.
echo   Open in your browser:
echo.
echo       http://localhost:5000
echo.
echo   On your phone (same WiFi):
echo.
echo       http://192.168.0.11:5000
echo.
echo ======================================================================
echo   Press Ctrl+C to stop the server
echo ======================================================================
echo.

cd /d "%WEBAPP%"
python app.py

echo.
echo Server stopped.
pause

