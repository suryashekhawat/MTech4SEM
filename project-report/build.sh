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

Compile main.tex to main.pdf (tectonic, latexmk, or pdflatex).

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
    "/Library/TeX/texbin/pdflatex"
    "/usr/local/texlive/2024/bin/universal-darwin/pdflatex"
    "/usr/local/texlive/2023/bin/universal-darwin/pdflatex"
    "/c/Program Files/MiKTeX/miktex/bin/x64/pdflatex.exe"
    "${LOCALAPPDATA:-}/Programs/MiKTeX/miktex/bin/x64/pdflatex.exe"
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

create_valid_minimal_png() {
  local out="$1"
  python3 - "$out" <<'PY'
import struct
import sys
import zlib
from pathlib import Path


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    payload = chunk_type + data
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", zlib.crc32(payload) & 0xFFFFFFFF)
    )


def write_minimal_png(path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + b"\xcc\xcc\xcc"
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", ihdr)
    png += png_chunk(b"IDAT", zlib.compress(raw))
    png += png_chunk(b"IEND", b"")
    path.write_bytes(png)


write_minimal_png(Path(sys.argv[1]))
PY
}

create_placeholder_png() {
  local out="$1"
  if [[ -f "$out" ]]; then
    return 0
  fi
  if [[ "$out" == "system_architecture.png" ]] && [[ -f "$SCRIPT_DIR/generate_architecture_png.py" ]]; then
    if python3 "$SCRIPT_DIR/generate_architecture_png.py"; then
      echo "Created architecture diagram: $out"
      return 0
    fi
  fi
  if command -v python3 >/dev/null 2>&1; then
    create_valid_minimal_png "$out"
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

if [[ ! -f system_architecture.png ]] || ! python3 -c "
import struct, sys, zlib
from pathlib import Path
p = Path('system_architecture.png')
if not p.exists():
    sys.exit(1)
d = p.read_bytes()
pos = 8
while pos + 12 <= len(d):
    ln = struct.unpack('>I', d[pos:pos+4])[0]
    ct = d[pos+4:pos+8]
    data = d[pos+8:pos+8+ln]
    crc = struct.unpack('>I', d[pos+8+ln:pos+12+ln])[0]
    if zlib.crc32(ct + data) & 0xFFFFFFFF != crc:
        sys.exit(1)
    pos += 12 + ln
    if ct == b'IEND':
        break
" 2>/dev/null; then
  if $PLACEHOLDERS || [[ ! -f system_architecture.png ]]; then
    create_placeholder_png system_architecture.png
  fi
fi

if command -v tectonic >/dev/null 2>&1; then
  echo "Building with tectonic..."
  tectonic -X compile "$TEX_FILE"
  if $CLEAN; then
    rm -f main.aux main.log main.out main.toc main.lof main.lot main.fls main.fdb_latexmk
  fi
elif command -v latexmk >/dev/null 2>&1; then
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
