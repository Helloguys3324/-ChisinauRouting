@echo off
chcp 65001 >nul
cls
echo.
echo ============================================================
echo   STOPPING CHIȘINĂU ROUTING ENGINE
echo ============================================================
echo.

REM Find process on port 5000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    set PID=%%a
    goto :found
)

echo   [!] Server not running on port 5000
echo.
pause
exit /b

:found
echo   [*] Found server process: %PID%
echo   [*] Stopping...
taskkill /F /PID %PID% >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   [OK] Server stopped successfully
) else (
    echo   [!] Failed to stop server
)
echo.
pause
