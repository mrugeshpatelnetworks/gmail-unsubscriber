#!/usr/bin/env bash
# Email Unsubscriber — Mac/Linux Auto-Setup (Gmail + Yahoo)
# Works whether launched from terminal, double-clicked, or run from any directory.

# ── Always run from the folder this script lives in ──────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "============================================="
echo "  Gmail Unsubscriber - Mac/Linux Auto-Setup"
echo "============================================="
echo ""
echo "Running from: $SCRIPT_DIR"
echo ""

# ─────────────────────────────────────────────
# Verify required files are present
# ─────────────────────────────────────────────
MISSING=0
for FILE in "gmail_unsubscriber.py" "requirements.txt"; do
    if [ ! -f "$FILE" ]; then
        echo "[ERROR] $FILE not found in $SCRIPT_DIR"
        MISSING=1
    fi
done
if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "Make sure you extracted ALL files from the ZIP before running setup."
    echo "Expected files in the same folder as setup.sh:"
    echo "  - gmail_unsubscriber.py"
    echo "  - requirements.txt"
    echo ""
    read -rp "Press Enter to exit..."
    exit 1
fi

# ─────────────────────────────────────────────
# STEP 1 — Find or install Python 3.9+
# ─────────────────────────────────────────────
echo "[1/4] Checking for Python..."

PYTHON=""

_py_ok() {
    local cmd="$1"
    command -v "$cmd" &>/dev/null || return 1
    local major minor
    major=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null) || return 1
    minor=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null) || return 1
    [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]
}

_py_ok python3 && PYTHON="python3"
[ -z "$PYTHON" ] && _py_ok python && PYTHON="python"

# ── Install Python if not found ──────────────────────────────────────────────
if [ -z "$PYTHON" ]; then
    echo "       Python 3.9+ not found. Installing automatically..."
    echo ""
    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        echo "       Detected: macOS"
        if ! command -v brew &>/dev/null; then
            echo "       Installing Homebrew (Mac package manager)..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            [ -f "/opt/homebrew/bin/brew" ] && eval "$(/opt/homebrew/bin/brew shellenv)"
            [ -f "/usr/local/bin/brew"    ] && eval "$(/usr/local/bin/brew shellenv)"
        fi
        echo "       Installing Python via Homebrew..."
        brew install python@3.12
        PYTHON="python3"

    elif [ "$OS" = "Linux" ]; then
        echo "       Detected: Linux"
        if command -v apt-get &>/dev/null; then
            echo "       Using apt (Ubuntu/Debian)..."
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv
        elif command -v dnf &>/dev/null; then
            echo "       Using dnf (Fedora/RHEL)..."
            sudo dnf install -y python3 python3-pip
        elif command -v pacman &>/dev/null; then
            echo "       Using pacman (Arch)..."
            sudo pacman -Sy --noconfirm python python-pip
        elif command -v zypper &>/dev/null; then
            echo "       Using zypper (openSUSE)..."
            sudo zypper install -y python3 python3-pip
        else
            echo ""
            echo "[ERROR] Could not detect your package manager."
            echo "Please install Python 3.9+ from https://python.org, then run this script again."
            read -rp "Press Enter to exit..."
            exit 1
        fi
        PYTHON="python3"
    fi
fi

if [ -z "$PYTHON" ] || ! $PYTHON --version &>/dev/null; then
    echo ""
    echo "[ERROR] Could not find or install Python."
    echo "Please install Python 3.9+ from https://python.org, then run this script again."
    read -rp "Press Enter to exit..."
    exit 1
fi

echo "       Found: $($PYTHON --version)"
echo ""

# ─────────────────────────────────────────────
# STEP 2 — Create virtual environment
# ─────────────────────────────────────────────
echo "[2/4] Setting up virtual environment..."

VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ -f "$VENV_PYTHON" ]; then
    echo "       Existing virtual environment found — reusing it."
else
    echo "       Creating .venv/ in $SCRIPT_DIR..."
    $PYTHON -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Failed to create virtual environment."
        echo "Try: $PYTHON -m pip install --user virtualenv"
        read -rp "Press Enter to exit..."
        exit 1
    fi
    echo "       Virtual environment created!"
fi

# ─────────────────────────────────────────────
# STEP 3 — Install dependencies into venv
# ─────────────────────────────────────────────
echo ""
echo "[3/4] Installing dependencies..."
echo "       (PySide6, Google Auth — first run may take a few minutes)"
echo ""

"$VENV_PYTHON" -m pip install --upgrade pip --quiet
"$VENV_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Failed to install dependencies."
    echo "Try: $VENV_PYTHON -m pip install -r requirements.txt"
    read -rp "Press Enter to exit..."
    exit 1
fi

echo "       All dependencies installed!"

# ─────────────────────────────────────────────
# STEP 4 — Show detected credentials + launch
# ─────────────────────────────────────────────
echo ""
echo "[4/4] Checking for saved credentials (Gmail + Yahoo)..."

FOUND_CREDS=0
for VAR in GMAIL_EMAIL GMAIL_USER GOOGLE_EMAIL \
           GMAIL_EMAIL_1 GMAIL_EMAIL_2 GMAIL_EMAIL_3 \
           GMAIL_USER_1  GMAIL_USER_2  GMAIL_USER_3; do
    VALUE="${!VAR:-}"
    if [ -n "$VALUE" ]; then
        echo "       Gmail:  $VALUE"
        FOUND_CREDS=1
    fi
done
for VAR in YAHOO_EMAIL YAHOO_USER \
           YAHOO_EMAIL_1 YAHOO_EMAIL_2 YAHOO_EMAIL_3; do
    VALUE="${!VAR:-}"
    if [ -n "$VALUE" ]; then
        echo "       Yahoo:  $VALUE"
        FOUND_CREDS=1
    fi
done

if [ "$FOUND_CREDS" -eq 1 ]; then
    echo "       These will be auto-filled in the app."
else
    echo "       No saved credentials found."
    echo "       You can enter them manually in the app, or add these to"
    echo "       ~/.zshrc (Mac) or ~/.bashrc (Linux) for auto-fill next time:"
    echo ""
    echo "         Gmail:"
    echo "           export GMAIL_EMAIL=\"you@gmail.com\""
    echo "           export GMAIL_APP_PASSWORD=\"xxxx xxxx xxxx xxxx\""
    echo ""
    echo "         Yahoo:"
    echo "           export YAHOO_EMAIL=\"you@yahoo.com\""
    echo "           export YAHOO_APP_PASSWORD=\"xxxx xxxx xxxx xxxx\""
fi

echo ""
echo "============================================="
echo "  Launching Email Unsubscriber..."
echo "============================================="
echo ""
"$VENV_PYTHON" "$SCRIPT_DIR/gmail_unsubscriber.py"

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] The app closed with an error."
    echo "Please screenshot everything above and report it."
    read -rp "Press Enter to exit..."
fi
