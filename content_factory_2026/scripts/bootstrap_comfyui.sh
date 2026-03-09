#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p external

if [[ ! -d external/ComfyUI ]]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git external/ComfyUI
fi

python3 -m venv external/ComfyUI/.venv
source external/ComfyUI/.venv/bin/activate
pip install --upgrade pip
pip install -r external/ComfyUI/requirements.txt

echo "✅ ComfyUI prêt (sans modèles)."
echo "Ajoute tes checkpoints dans external/ComfyUI/models/checkpoints"
echo "Run: cd external/ComfyUI && source .venv/bin/activate && python main.py --listen 127.0.0.1 --port 8188"
