#!/usr/bin/env bash
echo "========================================="
echo " Gmail Unsubscriber - Mac/Linux Setup"
echo "========================================="
echo

# ── Find Python ───────────────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON=python
else
    echo "[ERROR] Python 3 not found."
    echo "Install it first:"
    echo "  Mac:    brew install python    (or download from https://python.org)"
    echo "  Ubuntu: sudo apt install python3 python3-pip"
    echo "  Fedora: sudo dnf install python3"
    exit 1
fi

echo "Using: $($PYTHON --version)"
echo

# ── Install dependencies ──────────────────────────────────────────────────────
echo "[1/2] Installing dependencies..."
$PYTHON -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo
    echo "[ERROR] pip install failed. Try running manually:"
    echo "  pip3 install -r requirements.txt"
    exit 1
fi

echo
echo "[2/2] Starting Gmail Unsubscriber..."
echo
$PYTHON gmail_unsubscriber.py
