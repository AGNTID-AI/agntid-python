#!/usr/bin/env bash
# Local development setup for AgntID SDK.
#
# Creates a venv under .venv and installs the SDK in editable mode with all
# extras (MSK, MCP, dev).
#
# Run from repo root or SDK directory — the script resolves paths relative to
# its own location.
#
# Usage:
#   ./scripts/setup-dev.sh

set -euo pipefail

SDK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$SDK_DIR/.venv"

# ---------- Find Python 3.10+ ----------
PYTHON=""
for py in python3.11 python3.12 python3.10 python3; do
  if command -v "$py" &>/dev/null; then
    ver="$("$py" -c 'import sys; print(sys.version_info[:2])')"
    major="$("$py" -c 'import sys; print(sys.version_info[0])')"
    minor="$("$py" -c 'import sys; print(sys.version_info[1])')"
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON="$py"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.10+ not found. Install Python 3.10/3.11/3.12 and ensure it is on PATH." >&2
  exit 1
fi

echo "Using $PYTHON ($("$PYTHON" --version))"
echo "SDK dir:  $SDK_DIR"
echo "Venv dir: $VENV_DIR"
echo ""

# ---------- Create / refresh venv ----------
if [ -d "$VENV_DIR" ]; then
  echo "Existing venv found — upgrading pip and reinstalling..."
else
  echo "Creating venv..."
  "$PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip -q

# ---------- Install SDK with all extras ----------
echo "Installing agntid-sdk[dev,msk] (editable)..."
"$VENV_DIR/bin/pip" install -e "$SDK_DIR[dev,msk]" -q

echo ""
echo "Setup complete."
echo ""
echo "Activate the venv:"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "Run examples:"
echo "  python $SDK_DIR/examples/msk/msk_demo.py --help"
echo "  python $SDK_DIR/examples/fastmcp/openai_demo.py --help"
echo ""
echo "Run tests:"
echo "  cd $SDK_DIR && make test"
