#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "========================================================"
echo "       HTML Tester - Standalone Autonomous Agent        "
echo "========================================================"

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 could not be found."
    exit 1
fi

if [ -d ".venv" ]; then
    if ! .venv/bin/python -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
        echo "[!] Existing virtual environment is invalid (possibly due to directory relocation)."
        echo "[*] Rebuilding virtual environment (.venv)..."
        rm -rf .venv
    fi
fi

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "[*] Verifying dependencies..."
python -m pip install -q -r requirements.txt
if ! python -c "from core.browser_runner import BrowserRunner; from pathlib import Path; r=BrowserRunner(Path('output/artifacts')); ch=r.detect_available_channel(); from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True, channel=ch) if ch else p.chromium.launch(headless=True); b.close(); p.stop()" >/dev/null 2>&1; then
    echo "[*] Setting up Playwright browser binary..."
    python -m playwright install chromium
fi

echo "[*] Launching HTML Tester..."
python html_tester.py "$@"
