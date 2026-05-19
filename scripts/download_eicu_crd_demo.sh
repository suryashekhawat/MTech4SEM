#!/usr/bin/env bash
# Start eICU-CRD demo download in the background (Git Bash / WSL / Linux / macOS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${ROOT}/data/eicu-crd-demo"
LOG_FILE="${OUT_DIR}/download.log"
PID_FILE="${OUT_DIR}/download.pid"
SCRIPT="${ROOT}/scripts/download_eicu_crd_demo.py"

mkdir -p "${OUT_DIR}"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}")"
  if kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "Download already running (PID ${OLD_PID})."
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

PYTHON=""
for candidate in python python3 /c/Python311/python; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    PYTHON="${candidate}"
    break
  fi
done

if [[ -z "${PYTHON}" ]]; then
  echo "Error: Python not found. Install Python 3 and retry." >&2
  exit 1
fi

nohup "${PYTHON}" "${SCRIPT}" --log-file "${LOG_FILE}" >/dev/null 2>&1 &
echo $! > "${PID_FILE}"

echo "eICU-CRD demo download started in background."
echo "  PID:  $(cat "${PID_FILE}")"
echo "  Log:  ${LOG_FILE}"
echo "  Data: ${OUT_DIR}"
echo ""
echo "Tail progress:  tail -f \"${LOG_FILE}\""
echo "Check running:  kill -0 \$(cat \"${PID_FILE}\") && echo still running"
