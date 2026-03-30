@echo off
REM ============================================================
REM Chisinau Routing Engine - Quick Start Script
REM ============================================================

set PGROOT=D:\PostgreSQL\pgsql
set PGDATA=D:\PostgreSQL\data
set PGBIN=%PGROOT%\bin
set VENV=D:\ChisinauRouting\ingestion\venv

REM Add PostgreSQL to PATH
set PATH=%PGBIN%;%PATH%

if "%1"=="start" goto start_all
if "%1"=="stop" goto stop_all
if "%1"=="status" goto status
if "%1"=="psql" goto psql
if "%1"=="gtfsrt" goto gtfsrt_worker
if "%1"=="tomtom" goto tomtom_worker

echo.
echo ============================================================
echo Chisinau Routing Engine - Management Script
echo ============================================================
echo.
echo Usage: routing.bat [command]
echo.
echo Commands:
echo   start   - Start PostgreSQL server
echo   stop    - Stop PostgreSQL server  
echo   status  - Show database status
echo   psql    - Open PostgreSQL shell
echo   gtfsrt  - Start GTFS-RT telemetry worker
echo   tomtom  - Start TomTom traffic worker
echo.
goto end

:start_all
echo Starting PostgreSQL...
"%PGBIN%\pg_ctl.exe" start -D "%PGDATA%" -l "D:\PostgreSQL\postgresql.log"
echo.
echo PostgreSQL started! Connect using:
echo   Host: localhost
echo   Port: 5432
echo   Database: chisinau_routing
echo   User: chisinau
echo   Password: routing_engine_2024
goto end

:stop_all
echo Stopping PostgreSQL...
"%PGBIN%\pg_ctl.exe" stop -D "%PGDATA%"
goto end

:status
echo.
echo === PostgreSQL Status ===
"%PGBIN%\pg_ctl.exe" status -D "%PGDATA%"
echo.
echo === Database Stats ===
"%PGBIN%\psql.exe" -U chisinau -d chisinau_routing -c "SELECT 'Nodes' as entity, COUNT(*) FROM nodes UNION ALL SELECT 'Edges', COUNT(*) FROM edges UNION ALL SELECT 'Telemetry Records', COUNT(*) FROM trolleybus_telemetry UNION ALL SELECT 'Traffic Records', COUNT(*) FROM tomtom_traffic;"
goto end

:psql
"%PGBIN%\psql.exe" -U chisinau -d chisinau_routing
goto end

:gtfsrt_worker
echo Starting GTFS-RT Worker (Roataway trolleybus telemetry)...
call "%VENV%\Scripts\activate.bat"
cd /d D:\ChisinauRouting\ingestion
python gtfsrt_worker.py
goto end

:tomtom_worker
echo Starting TomTom Traffic Worker...
call "%VENV%\Scripts\activate.bat"
cd /d D:\ChisinauRouting\ingestion
python tomtom_worker.py
goto end

:end
