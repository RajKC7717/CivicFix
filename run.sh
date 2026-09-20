#!/usr/bin/env bash
# Start NagarNetra (PS-18 CivicFix) - API + web app, in one command.
# First run also sets up the venv, data, model and demo database.
# Works with no API key and no internet.
#
#   ./run.sh            set up if needed, then start both servers
#   ./run.sh --reseed   rebuild the demo dataset first
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
# Marathi and Hindi text reaches the log handlers; force UTF-8 so they cannot crash.
export PYTHONIOENCODING=utf-8

if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"   # Git Bash on Windows
elif [ -x ".venv/bin/python" ];      then PY=".venv/bin/python"
else
  echo "==> Creating .venv"
  (python3.11 -m venv .venv 2>/dev/null || python3 -m venv .venv || python -m venv .venv)
  PY="$([ -x .venv/bin/python ] && echo .venv/bin/python || echo .venv/Scripts/python.exe)"
  "$PY" -m pip install --upgrade pip -q
fi

echo "==> Installing backend dependencies"
"$PY" -m pip install -q -r backend/requirements-dev.txt
"$PY" -m pip install -q cryptography

[ -f .env ] || { echo "==> Creating .env"; cp .env.example .env; }

echo "==> Preparing data"
[ -f data/wards.geojson ]             || "$PY" scripts/build_wards.py
[ -f data/synthetic_complaints.csv ]  || "$PY" scripts/generate_synthetic.py
[ -f backend/var/models/fallback_clf.joblib ] || {
  echo "    training the offline classifier (about 20s)"; "$PY" scripts/train_fallback.py >/dev/null; }
if [ "${1:-}" = "--reseed" ] || [ ! -f backend/var/nagarnetra.db ]; then
  echo "    seeding the demo database"; "$PY" scripts/seed_db.py --reset
fi

echo "==> Installing frontend dependencies"
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)

echo ""
echo "  Citizen app      http://localhost:5173"
echo "  Officer console  http://localhost:5173/admin    (officer / officer)"
echo "  API docs         http://127.0.0.1:8000/docs"
echo ""

"$PY" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM
cd frontend && npm run dev
