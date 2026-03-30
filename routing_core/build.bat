@echo off
REM ============================================================
REM Build C++ Routing Core
REM ============================================================

set CMAKE_PATH=D:\ChisinauRouting\tools\cmake\bin
set PATH=%CMAKE_PATH%;%PATH%

cd /d D:\ChisinauRouting\routing_core

echo.
echo ============================================================
echo Building C++ Routing Core
echo ============================================================
echo.
echo NOTE: You need a C++ compiler (MSVC or MinGW) to build.
echo.
echo If you don't have one, install Visual Studio Build Tools:
echo https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo.

REM Create build directory
if not exist build mkdir build
cd build

REM Configure
echo Configuring with CMake...
cmake .. -G "Visual Studio 17 2022" -A x64

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo CMake configuration failed. 
    echo Trying MinGW Makefiles instead...
    cmake .. -G "MinGW Makefiles"
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo ERROR: No C++ compiler found!
    echo ============================================================
    echo.
    echo Please install one of:
    echo 1. Visual Studio Build Tools (recommended)
    echo 2. MinGW-w64
    echo.
    pause
    exit /b 1
)

REM Build
echo.
echo Building...
cmake --build . --config Release

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================================
    echo BUILD SUCCESSFUL!
    echo ============================================================
    echo.
    echo Binary: D:\ChisinauRouting\routing_core\build\Release\routing_server.exe
) else (
    echo.
    echo Build failed. Check errors above.
)

pause
