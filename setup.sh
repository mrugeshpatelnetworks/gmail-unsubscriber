#!/usr/bin/env bash
set -e

echo "========================================"
echo " Gmail Unsubscriber - Linux/Mac Setup   "
echo "========================================"
echo

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found."
    echo "Install it from https://python.org or via your package manager:"
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON=$(command -v python3)
echo "Python: $($PYTHON --version)"

# Create and activate a virtual environment (keeps your system clean)
if [ ! -d ".venv" ]; then
    echo
    echo "[1/3] Creating virtual environment..."
    $PYTHON -m venv .venv
fi

echo "[2/3] Installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "[3/3] Starting Gmail Unsubscriber..."
echo
python gmail_unsubscriber.py
