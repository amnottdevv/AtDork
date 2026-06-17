#!/usr/bin/env bash
# AtDork Setup Script
# Installs Python if missing, builds from pyproject.toml, or falls back to requirements.txt

set -e

echo "========================================="
echo "  AtDork v1.3.2 - Setup"
echo "========================================="
echo ""

# ── Check Python ──────────────────────────────────────────────────────
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[!] Python not found. Installing Python..."
    # Detect OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt &>/dev/null; then
            sudo apt update && sudo apt install -y python3 python3-pip
        elif command -v yum &>/dev/null; then
            sudo yum install -y python3 python3-pip
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3 python3-pip
        else
            echo "[✗] Unsupported Linux distribution. Please install Python manually."
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            brew install python3
        else
            echo "[✗] Homebrew not found. Please install Python manually from https://www.python.org/downloads/"
            exit 1
        fi
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        echo "[✗] Windows detected. Please install Python manually from https://www.python.org/downloads/"
        exit 1
    else
        echo "[✗] Unknown OS. Please install Python manually."
        exit 1
    fi
    PYTHON=python3
fi

echo "[✓] Python found: $($PYTHON --version)"
echo ""

# ── Check pip ─────────────────────────────────────────────────────────
if ! $PYTHON -m pip --version &>/dev/null; then
    echo "[!] pip not found. Installing pip..."
    $PYTHON -m ensurepip --upgrade
fi
echo "[✓] pip found: $($PYTHON -m pip --version | head -1)"
echo ""

# ── Install from pyproject.toml ───────────────────────────────────────
echo "[*] Attempting to install AtDork from pyproject.toml..."
if $PYTHON -m pip install . --quiet 2>/dev/null; then
    echo "[✓] AtDork installed successfully from pyproject.toml!"
    echo ""
    echo "    You can now run: atdork --version"
    echo ""
else
    echo "[!] Could not install from pyproject.toml."
    echo "[*] Falling back to requirements.txt..."
    echo ""

    # ── Fallback: install dependencies only ────────────────────────────
    if [ -f "requirements.txt" ]; then
        $PYTHON -m pip install -r requirements.txt
        echo ""
        echo "[✓] Dependencies installed from requirements.txt."
        echo ""
        echo "    You can run: $PYTHON atdork.py --version"
    else
        echo "[✗] requirements.txt not found. Please check your installation."
        exit 1
    fi
fi

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
