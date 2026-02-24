@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Multi-Agent CLI Windows Startup Script
:: ============================================================

:: Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
cd /d "%ROOT_DIR%"
set "ROOT_DIR=%CD%"

set "RUN_DIR=%ROOT_DIR%\.run"
set "LOG_DIR=%RUN_DIR%\logs"
set "PID_FILE=%RUN_DIR%\start-all.pids"

set "BACKEND_DIR=%ROOT_DIR%\backend"
set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "BACKEND_LOG_CONFIG=%BACKEND_DIR%\logging.ini"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=5173"

:: Create directories
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: Check if already running
if exist "%PID_FILE%" (
    echo [INFO] Checking existing PID file...
    set "active_found=0"
    for /f "tokens=1,2 delims=:" %%a in (%PID_FILE%) do (
        if not "%%b"=="" (
            tasklist /FI "PID eq %%b" 2>nul | findstr /I "%%b" >nul
            if !errorlevel! equ 0 (
                set "active_found=1"
            )
        )
    )
    if "!active_found!"=="1" (
        echo [ERROR] Detected running processes from previous start.
        echo Please run stop-all.bat first or manually stop the processes.
        exit /b 1
    ) else (
        del /f "%PID_FILE%" 2>nul
    )
)

:: ============================================================
:: Backend Setup
:: ============================================================

:: Check Python availability
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+ first.
    exit /b 1
)

:: Check if venv exists, if not create it
if not exist "%BACKEND_DIR%\venv\Scripts\activate.bat" (
    echo [INFO] Virtual environment not found. Creating one...
    cd /d "%BACKEND_DIR%"
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: Check if dependencies are installed
if not exist "%BACKEND_DIR%\venv\Scripts\uvicorn.exe" (
    echo [INFO] Installing backend dependencies...
    cd /d "%BACKEND_DIR%"
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install backend dependencies.
        exit /b 1
    )
    echo [OK] Backend dependencies installed.
)

:: Set uvicorn command to use venv
set "uvicorn_cmd=%BACKEND_DIR%\venv\Scripts\uvicorn.exe"

:: ============================================================
:: Frontend Setup
:: ============================================================

:: Check npm availability
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] npm not found. Please install Node.js/npm first.
    exit /b 1
)

:: Check if node_modules exists
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies...
    cd /d "%FRONTEND_DIR%"
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install frontend dependencies.
        exit /b 1
    )
    echo [OK] Frontend dependencies installed.
)

:: ============================================================
:: Port Check
:: ============================================================

call :check_port_available "Backend" %BACKEND_PORT%
if %errorlevel% neq 0 exit /b 1

call :check_port_available "Frontend" %FRONTEND_PORT%
if %errorlevel% neq 0 exit /b 1

:: ============================================================
:: Start Services
:: ============================================================

:: Clear log files
echo. > "%LOG_DIR%\backend.log"
echo. > "%LOG_DIR%\frontend.log"

:: Create empty PID file
echo. > "%PID_FILE%"

:: Start backend
echo [INFO] Starting backend...
cd /d "%BACKEND_DIR%"
start "Multi-Agent Backend" /min cmd /c "call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT% --log-config "%BACKEND_LOG_CONFIG%" >> "%LOG_DIR%\backend.log" 2>&1"
timeout /t 3 /nobreak >nul

:: Find backend PID by window title
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Multi-Agent Backend*" /FO LIST 2^>nul ^| findstr "PID:"') do (
    echo backend:%%a >> "%PID_FILE%"
    echo [OK] Backend started (PID=%%a, log=%LOG_DIR%\backend.log)
    goto :backend_started
)
:backend_started

:: Start frontend
echo [INFO] Starting frontend...
cd /d "%FRONTEND_DIR%"
start "Multi-Agent Frontend" /min cmd /c "npm run dev -- --host 0.0.0.0 --port %FRONTEND_PORT% >> "%LOG_DIR%\frontend.log" 2>&1"
timeout /t 3 /nobreak >nul

:: Find frontend PID by window title
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq Multi-Agent Frontend*" /FO LIST 2^>nul ^| findstr "PID:"') do (
    echo frontend:%%a >> "%PID_FILE%"
    echo [OK] Frontend started (PID=%%a, log=%LOG_DIR%\frontend.log)
    goto :frontend_started
)
:frontend_started

:: Wait for services to be ready
echo [INFO] Waiting for services to be ready...
call :wait_for_port "Backend" "127.0.0.1" %BACKEND_PORT% 30
if %errorlevel% neq 0 (
    echo [ERROR] Backend failed to start within 30s. Check log: %LOG_DIR%\backend.log
    type "%LOG_DIR%\backend.log"
    exit /b 1
)

call :wait_for_port "Frontend" "127.0.0.1" %FRONTEND_PORT% 30
if %errorlevel% neq 0 (
    echo [ERROR] Frontend failed to start within 30s. Check log: %LOG_DIR%\frontend.log
    exit /b 1
)

echo.
echo ========================================
echo All services started successfully:
echo - Backend:  http://localhost:%BACKEND_PORT%
echo - Frontend: http://localhost:%FRONTEND_PORT%
echo ========================================
echo.
echo Log directory: %LOG_DIR%
echo PID file: %PID_FILE%
echo.
echo Press Ctrl+C to stop monitoring (services will continue running)
echo Run stop-all.bat to stop all services.
echo.

:: Monitor processes
:monitor_loop
timeout /t 5 /nobreak >nul

set "failed=0"
for /f "tokens=1,2 delims=:" %%a in (%PID_FILE%) do (
    if not "%%b"=="" (
        tasklist /FI "PID eq %%b" 2>nul | findstr /I "%%b" >nul
        if !errorlevel! neq 0 (
            echo [ERROR] %%a process (PID=%%b) has exited. Check log: %LOG_DIR%\%%a.log
            set "failed=1"
        )
    )
)

if "%failed%"=="1" (
    echo [ERROR] One or more processes have failed. Exiting.
    exit /b 1
)

goto :monitor_loop

:: ============================================================
:: Functions
:: ============================================================

:check_port_available
set "port_name=%~1"
set "port_num=%~2"
netstat -ano | findstr ":%port_num% " | findstr "LISTENING" >nul
if %errorlevel% equ 0 (
    echo [ERROR] %port_name% port %port_num% is already in use.
    netstat -ano | findstr ":%port_num% " | findstr "LISTENING"
    exit /b 1
)
exit /b 0

:wait_for_port
set "svc_name=%~1"
set "host=%~2"
set "port=%~3"
set "timeout=%~4"

for /l %%i in (1,1,%timeout%) do (
    powershell -Command "(New-Object Net.Sockets.TcpClient).Connect('%host%', %port%)" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] %svc_name% is ready on port %port%
        exit /b 0
    )
    timeout /t 1 /nobreak >nul
)
echo [ERROR] %svc_name% did not become ready within %timeout%s
exit /b 1

endlocal
