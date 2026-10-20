@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
title HTML Tester Agent

echo ========================================================
echo        HTML Tester - Standalone Autonomous Agent
echo ========================================================

:: 1. Check Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found on PATH!
    echo Please install Python 3.10+ from https://www.python.org/
    pause
    exit /b 1
)

:: 2. Auto-initialize Virtual Environment if missing or broken due to relocation
set VENV_OK=0
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -c "import sys; sys.exit(0)" >nul 2>nul
    if !ERRORLEVEL! EQU 0 (
        set VENV_OK=1
    ) else (
        echo [!] Existing virtual environment is invalid (possibly due to directory relocation).
        echo [*] Rebuilding virtual environment...
        rmdir /s /q .venv >nul 2>nul
    )
)

if !VENV_OK! EQU 0 (
    echo [*] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

:: 3. Install Dependencies & Ensure Browser
echo [*] Verifying dependencies...
python -m pip install -q -r requirements.txt
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop()" >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [*] Setting up Playwright browser binary...
    python -m playwright install chromium
)

:: 4. Run html_tester
echo [*] Launching HTML Tester...
python html_tester.py %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% NEQ 0 (
    echo.
    echo ========================================================
    echo [EXECUTION ANOMALY DETECTED] [Exit Code: %EXIT_CODE%]
    echo.
    echo [Easy Fix Guide]
    echo You can simply copy the error text above
    echo and paste it directly back to the AI developer to get a patch!
    echo ========================================================
    echo.
    pause
) else (
    echo.
    echo ========================================================
    echo [OK] Execution completed successfully.
    echo Please check the output directory for your test reports!
    echo ========================================================
    echo.
    pause
)
