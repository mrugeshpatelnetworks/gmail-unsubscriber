#!/usr/bin/env bash
# Gmail Unsubscriber - Mac/Linux Auto-Setup
# Works on macOS (Intel + Apple Silicon) and Ubuntu/Debian/Fedora Linux

# Change to the script's own directory so it works when double-clicked
cd "$(dirname "$0")"

echo ""
echo "============================================="
echo "  Gmail Unsubscriber - Mac/Linux Auto-Setup"
echo "============================================="
echo ""

# ─────────────────────────────────────────────
# STEP 1 — Find or install Python 3
# ─────────────────────────────────────────────
echo "[1/3] Checking for Python..."

PYTHON=""

# Check for python3
if command -v python3 &>/dev/null; then
    VER=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
    if [ "${VER:-0}" -ge 9 ] 2>/dev/null; then
        PYTHON="python3"
    fi
fi

# Check for python (some systems use this for Python 3)
if [ -z "$PYTHON" ] && command -v python &>/dev/null; then
    MAJOR=$(python -c "import sys; print(sys.version_info.major)" 2>/dev/null)
    VER=$(python -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
    if [ "${MAJOR:-0}" -eq 3 ] && [ "${VER:-0}" -ge 9 ] 2>/dev/null; then
        PYTHON="python"
    fi
fi

# ── Install Python if not found ──────────────
if [ -z "$PYTHON" ]; then
    echo "       Python 3.9+ not found. Installing automatically..."
    echo ""

    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        # ── macOS ──────────────────────────────
        echo "       Detected: macOS"

        # Install Homebrew if missing
        if ! command -v brew &>/dev/null; then
            echo "       Installing Homebrew (Mac package manager)..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for Apple Silicon
            if [ -f "/opt/homebrew/bin/brew" ]; then
                eval "$(/opt/homebrew/bin/brew shellenv)"
            fi
        fi

        echo "       Installing Python via Homebrew..."
        brew install python@3.12
        PYTHON="python3"

    elif [ "$OS" = "Linux" ]; then
        # ── Linux ───────────────────────────────
        echo "       Detected: Linux"

        if command -v apt-get &>/dev/null; then
            # Ubuntu / Debian
            echo "       Installing Python via apt..."
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv

        elif command -v dnf &>/dev/null; then
            # Fedora / RHEL / CentOS
            echo "       Installing Python via dnf..."
            sudo dnf install -y python3 python3-pip

        elif command -v pacman &>/dev/null; then
            # Arch Linux
            echo "       Installing Python via pacman..."
            sudo pacman -Sy --noconfirm python python-pip

        else
            echo ""
            echo "[ERROR] Could not detect your package manager."
            echo "Please install Python 3.9+ manually, then run this script again."
            echo "  https://python.org/downloads"
            read -p "Press Enter to exit..."
            exit 1
        fi

        PYTHON="python3"
    fi
fi

# Verify we have Python now
if [ -z "$PYTHON" ] || ! $PYTHON --version &>/dev/null; then
    echo ""
    echo "[ERROR] Could not find or install Python."
    echo "Please install Python 3.9+ from https://python.org, then run this script again."
    read -p "Press Enter to exit..."
    exit 1
fi

echo "       Found: $($PYTHON --version)"
echo ""

# ─────────────────────────────────────────────
# STEP 2 — Install Python dependencies
# ─────────────────────────────────────────────
echo "[2/3] Installing dependencies (PySide6 + Gmail libraries)..."
echo "       This may take a few minutes on first run..."
echo ""

$PYTHON -m pip install --upgrade pip --quiet
$PYTHON -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Failed to install dependencies."
    echo "Try running manually: pip3 install -r requirements.txt"
    read -p "Press Enter to exit..."
    exit 1
fi

echo "       All dependencies installed!"
echo ""

# ─────────────────────────────────────────────
# STEP 3 — Launch the app
# ─────────────────────────────────────────────
echo "[3/3] Launching Gmail Unsubscriber..."
echo ""
$PYTHON gmail_unsubscriber.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] The app closed with an error."
    echo "Please screenshot the error above and report it."
    read -p "Press Enter to exit..."
fi
