@echo off
REM ============================================================
REM Clean up idle database connections
REM ============================================================

set PGBIN=D:\PostgreSQL\pgsql\bin

echo.
echo Cleaning up idle database connections...
echo.

"%PGBIN%\psql.exe" -U postgres -d chisinau_routing -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'chisinau_routing' AND usename = 'chisinau' AND state = 'idle' AND application_name = '';"

echo.
echo Remaining connections:
"%PGBIN%\psql.exe" -U chisinau -d chisinau_routing -c "SELECT COUNT(*) as active_connections FROM pg_stat_activity WHERE datname = 'chisinau_routing';"

echo.
echo Done!
pause
