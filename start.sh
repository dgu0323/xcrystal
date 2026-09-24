#!/bin/bash
# Start XCrystal analysis server (lives next to server.py / .env)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🚀 Starting XCrystal server..."
echo "📍 http://localhost:5678"
echo "📂 $DIR"
echo ""

# Resolve VENV_PATH: env var > .env > ./.venv  (expand leading ~)
_resolve_venv() {
  local v=""
  if [ -n "${VENV_PATH:-}" ]; then
    v="$VENV_PATH"
  elif [ -f .env ]; then
    # simple KEY=VALUE parse (first match); trim spaces and one layer of quotes
    v="$(grep -E '^[[:space:]]*VENV_PATH=' .env | head -1 | cut -d= -f2-)"
    # trim leading/trailing whitespace
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    # strip matching surrounding quotes
    if [ "${v#\"}" != "$v" ] && [ "${v%\"}" != "$v" ]; then
      v="${v#\"}"; v="${v%\"}"
    elif [ "${v#\'}" != "$v" ] && [ "${v%\'}" != "$v" ]; then
      v="${v#\'}"; v="${v%\'}"
    fi
  fi
  if [ -z "$v" ]; then
    v="./.venv"
  fi
  # Expand leading ~  (quote patterns so ~ is not expanded as $HOME in the match)
  case "$v" in
    '~') v="$HOME" ;;
    '~/'*) v="$HOME/${v:2}" ;;
  esac
  printf '%s\n' "$v"
}

VENV="$(_resolve_venv)"
echo "🐍 Venv: $VENV"

if [ ! -d "$VENV" ]; then
  echo "❌ Virtualenv missing at: $VENV"
  echo "   Create with:"
  echo "   python3 -m venv .venv"
  echo "   source .venv/bin/activate"
  echo "   pip install laya flask flask-cors"
  echo "   Or set VENV_PATH in .env / the environment."
  exit 1
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"
pip install flask flask-cors -q
python server.py
