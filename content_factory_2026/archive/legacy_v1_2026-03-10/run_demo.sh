#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

mkdir -p outputs
python3 src/demo_pipeline.py --topic "3 hooks qui convertissent pour PME locales" --out outputs

LATEST="$(ls -1dt outputs/demo_* | head -n 1)"
echo "\n=== Aperçu artefacts ==="
ls -la "$LATEST"
echo "\nScript:"
head -n 5 "$LATEST/script.txt"
