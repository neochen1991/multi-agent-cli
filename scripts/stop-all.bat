@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Multi-Agent CLI Windows Stop Script
:: ============================================================

:: Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
cd /d "%ROOT_DIR%"
set "ROOT_DIR=%CD%"

set "RUN_DIR=%ROOT_DIR%\.run"
set "PID_FILE=%RUN_DIR%\start-all.pids"

set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

echo [INFO] Stopping services...

:: Stop processes from PID file
if exist "%PID_FILE%" (
    echo [INFO] Reading PID file...
    for /f "tokens=1,2 delims=:" %%a in ('type "%PID_FILE%"') do (
        if not "%%b"=="" (
            echo [INFO] Stopping %%a (PID=%%b)...
            taskkill /PID %%b /F >nul 2>&1
        )
    )
    del /f "%PID_FILE%" 2>nul
    echo [OK] PID file removed.
) else (
    echo [INFO] PID file not found: %PID_FILE%
)

:: Kill by window title
echo [INFO] Stopping service windows...
taskkill /FI "WINDOWTITLE eq Multi-Agent Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Multi-Agent Frontend*" /F >nul 2>&1

:: Check for --force-ports argument
if "%~1"=="--force-ports" (
    echo [INFO] Force releasing ports: %BACKEND_PORT%/%FRONTEND_PORT%
    
    :: Kill processes on backend port
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
        echo [INFO] Killing process %%a on port %BACKEND_PORT%...
        taskkill /PID %%a /F >nul 2>&1
    )
    
    :: Kill processes on frontend port
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING" 2^>nul') do (
        echo [INFO] Killing process %%a on port %FRONTEND_PORT%...
        taskkill /PID %%a /F >nul 2>&1
    )
    
    echo [OK] Port cleanup complete.
)

echo.
echo [OK] Stop complete.
echo.

endlocal
