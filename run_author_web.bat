@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo      INTERACTIVE AUTHORING CMS & MULTI-FORMAT PUBLISHER
echo ============================================================
echo.

rem 1. Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8 or later and try again.
    goto end_error
)

rem 2. Check and setup virtual environment
if not exist ".venv" (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        goto end_error
    )
    echo [INFO] Installing required dependencies...
    call .venv\Scripts\pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies.
        goto end_error
    )
)

if not exist ".venv\Scripts\uvicorn.exe" (
    echo [ERROR] uvicorn.exe is missing from .venv\Scripts.
    echo Please delete the .venv folder and run run_author_web.bat again.
    goto end_error
)

echo [INFO] Starting web server on http://127.0.0.1:8080...
echo [INFO] Automatically opening dashboard in browser...
echo Press Ctrl+C in this window to stop the server when done.
echo.

rem Automatically open browser
start http://127.0.0.1:8080

rem Run the FastAPI app using uvicorn on port 8080
call .venv\Scripts\uvicorn app.web.author_server:app --host 127.0.0.1 --port 8080
if %errorlevel% neq 0 (
    echo [ERROR] Web server failed to start or crashed.
)

:end_error
echo.
echo ============================================================
echo Press any key to close this window...
echo ============================================================
pause >nul
