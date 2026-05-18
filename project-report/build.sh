#!/usr/bin/env bash
# Compile project-report/main.tex to main.pdf
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TEX_FILE="main.tex"
PDF_FILE="main.pdf"
PLACEHOLDERS=false
CLEAN=false

usage() {
  cat <<'EOF'
Usage: ./build.sh [OPTIONS]

Compile main.tex to main.pdf (runs pdflatex twice, or latexmk if available).

Options:
  --placeholders   Create minimal pes_logo.png / system_architecture.png if missing
  --clean          Remove auxiliary files after a successful build
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --placeholders) PLACEHOLDERS=true ;;
    --clean) CLEAN=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

find_pdflatex() {
  if command -v pdflatex >/dev/null 2>&1; then
    command -v pdflatex
    return 0
  fi
  local candidates=(
    "/c/Program Files/MiKTeX/miktex/bin/x64/pdflatex.exe"
    "$LOCALAPPDATA/Programs/MiKTeX/miktex/bin/x64/pdflatex.exe"
    "${USERPROFILE:-}/AppData/Local/Programs/MiKTeX/miktex/bin/x64/pdflatex.exe"
  )
  local c
  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      echo "$c"
      return 0
    fi
  done
  return 1
}

need_pdflatex() {
  PDFLATEX="$(find_pdflatex || true)"
  if [[ -z "$PDFLATEX" ]]; then
    echo "Error: pdflatex not found." >&2
    echo "Install TeX Live or MiKTeX and ensure pdflatex is on PATH." >&2
    echo "  Windows: https://miktex.org/download" >&2
    echo "  Or: choco install miktex" >&2
    exit 1
  fi
  export PDFLATEX
}

create_placeholder_png() {
  local out="$1"
  if [[ -f "$out" ]]; then
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    python - "$out" <<'PY'
import sys
from pathlib import Path

# Minimal valid 1x1 PNG (gray)
PNG = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
    0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
    0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
    0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D,
    0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
    0x44, 0xAE, 0x42, 0x60, 0x82,
])
Path(sys.argv[1]).write_bytes(PNG)
PY
    echo "Created placeholder: $out"
  else
    echo "Error: missing $out (use --placeholders with Python, or add the file manually)." >&2
    return 1
  fi
}

REQUIRED_IMAGES=(pes_logo.png system_architecture.png)
MISSING=()
for img in "${REQUIRED_IMAGES[@]}"; do
  [[ -f "$img" ]] || MISSING+=("$img")
done

if ((${#MISSING[@]} > 0)); then
  if $PLACEHOLDERS; then
    for img in "${MISSING[@]}"; do
      create_placeholder_png "$img"
    done
  else
    echo "Warning: missing image(s): ${MISSING[*]}"
    echo "  Add them to project-report/ or run: ./build.sh --placeholders"
    echo ""
  fi
fi

if command -v latexmk >/dev/null 2>&1; then
  echo "Building with latexmk..."
  latexmk -pdf -interaction=nonstopmode -file-line-error "$TEX_FILE"
  if $CLEAN; then
    latexmk -c "$TEX_FILE" >/dev/null 2>&1 || true
  fi
else
  need_pdflatex
  echo "Building with pdflatex (2 passes for TOC)..."
  "$PDFLATEX" -interaction=nonstopmode -file-line-error "$TEX_FILE"
  "$PDFLATEX" -interaction=nonstopmode -file-line-error "$TEX_FILE"
  if $CLEAN; then
    rm -f main.aux main.log main.out main.toc main.lof main.lot main.fls main.fdb_latexmk
  fi
fi

if [[ -f "$PDF_FILE" ]]; then
  echo ""
  echo "Success: $SCRIPT_DIR/$PDF_FILE"
else
  echo "Error: PDF was not produced. Check the log above." >&2
  exit 1
fi
