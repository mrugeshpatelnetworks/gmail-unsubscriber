#!/usr/bin/env bash
# Gmail Unsubscriber — Mac/Linux Auto-Setup
# Installs Python if missing, creates a virtual environment, installs deps, launches app.

# Always run from the script's own directory (works when double-clicked too)
cd "$(dirname "$0")"

echo ""
echo "============================================="
echo "  Gmail Unsubscriber - Mac/Linux Auto-Setup"
echo "============================================="
echo ""

# ─────────────────────────────────────────────
# STEP 1 — Find or install Python 3.9+
# ─────────────────────────────────────────────
echo "[1/4] Checking for Python..."

PYTHON=""

# Try python3 first
if command -v python3 &>/dev/null; then
    MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
    MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ] 2>/dev/null; then
        PYTHON="python3"
    fi
fi

# Try python (some systems alias it to Python 3)
if [ -z "$PYTHON" ] && command -v python &>/dev/null; then
    MINOR=$(python -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
    MAJOR=$(python -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
    if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 9 ] 2>/dev/null; then
        PYTHON="python"
    fi
fi

# ── Install Python if not found ──────────────────────────────────────────────
if [ -z "$PYTHON" ]; then
    echo "       Python 3.9+ not found. Installing automatically..."
    echo ""
    OS="$(uname -s)"

    if [ "$OS" = "Darwin" ]; then
        # ── macOS ─────────────────────────────────────────────────────────────
        echo "       Detected: macOS"

        if ! command -v brew &>/dev/null; then
            echo "       Installing Homebrew (Mac package manager)..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            # Add brew to PATH for Apple Silicon Macs
            [ -f "/opt/homebrew/bin/brew" ] && eval "$(/opt/homebrew/bin/brew shellenv)"
            [ -f "/usr/local/bin/brew"    ] && eval "$(/usr/local/bin/brew shellenv)"
        fi

        echo "       Installing Python via Homebrew..."
        brew install python@3.12

        # brew installs as python3
        PYTHON="python3"

    elif [ "$OS" = "Linux" ]; then
        # ── Linux ──────────────────────────────────────────────────────────────
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
            echo "Please install Python 3.9+ manually: https://python.org"
            read -rp "Press Enter to exit..."
            exit 1
        fi

        PYTHON="python3"
    fi
fi

# Final check
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

if [ -f ".venv/bin/python" ]; then
    echo "       Existing virtual environment found — reusing it."
else
    echo "       Creating virtual environment in .venv/..."
    $PYTHON -m venv .venv
    if [ $? -ne 0 ]; then
        echo ""
        echo "[ERROR] Failed to create virtual environment."
        echo "Try: $PYTHON -m pip install virtualenv && $PYTHON -m venv .venv"
        read -rp "Press Enter to exit..."
        exit 1
    fi
    echo "       Virtual environment created!"
fi

# Use the venv Python directly — no need to 'activate'
VENV_PYTHON=".venv/bin/python"

# ─────────────────────────────────────────────
# STEP 3 — Install dependencies into venv
# ─────────────────────────────────────────────
echo ""
echo "[3/4] Installing dependencies into virtual environment..."
echo "       (PySide6, Google Auth, IMAP libraries)"
echo "       First run may take a few minutes..."
echo ""

$VENV_PYTHON -m pip install --upgrade pip --quiet
$VENV_PYTHON -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Failed to install dependencies."
    echo "Try running manually: $VENV_PYTHON -m pip install -r requirements.txt"
    read -rp "Press Enter to exit..."
    exit 1
fi

echo "       All dependencies installed!"

# ─────────────────────────────────────────────
# STEP 4 — Show detected credentials + launch
# ─────────────────────────────────────────────
echo ""
echo "[4/4] Checking for saved Gmail credentials..."

FOUND_CREDS=0
for VAR in GMAIL_EMAIL GMAIL_USER GOOGLE_EMAIL \
           GMAIL_EMAIL_1 GMAIL_EMAIL_2 GMAIL_EMAIL_3 \
           GMAIL_USER_1  GMAIL_USER_2  GMAIL_USER_3; do
    VALUE="${!VAR:-}"
    if [ -n "$VALUE" ]; then
        echo "       Found: $VALUE"
        FOUND_CREDS=1
    fi
done

if [ "$FOUND_CREDS" -eq 1 ]; then
    echo "       These will be auto-filled in the app."
else
    echo "       No saved credentials found."
    echo "       You can enter them manually in the app, or save them"
    echo "       as environment variables for auto-fill next time:"
    echo ""
    echo "         export GMAIL_EMAIL=\"you@gmail.com\""
    echo "         export GMAIL_APP_PASSWORD=\"xxxx xxxx xxxx xxxx\""
    echo ""
    echo "       Add those lines to ~/.zshrc or ~/.bashrc to make them permanent."
fi

echo ""
echo "============================================="
echo "  Launching Gmail Unsubscriber..."
echo "============================================="
echo ""
$VENV_PYTHON gmail_unsubscriber.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] The app closed with an error."
    echo "Please screenshot everything above and report it."
    read -rp "Press Enter to exit..."
fi
