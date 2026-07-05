@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo           DIGITAL TEXTBOOK EPUB CONVERTER RUNNER
echo ============================================================
echo.

rem 1. Check Python installation
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.11 or later and try again.
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

rem 3. Ask for input file
echo Please select or drag-and-drop the Word document (.docx) to convert:
set /p docx_input="Input file path (e.g. docs/Ad_Making -Formatted.docx): "

:: Remove quotes if they drag and dropped the file
set docx_input=%docx_input:"=%

if "%docx_input%"=="" (
    echo [ERROR] No input file specified.
    goto end_error
)

if not exist "%docx_input%" (
    echo [ERROR] Input file does not exist at: %docx_input%
    goto end_error
)

echo.
echo [INFO] Starting pipeline execution...
call .venv\Scripts\python scripts/run_pipeline.py -i "%docx_input%"
if %errorlevel% neq 0 (
    echo [ERROR] Pipeline execution failed or encountered an error.
)

:end_error
echo.
echo ============================================================
echo Press any key to close this window...
echo ============================================================
pause >nul
