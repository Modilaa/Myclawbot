#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

echo "[1/6] Vérification prérequis système"
command -v python3 >/dev/null || { echo "python3 requis"; exit 1; }
command -v git >/dev/null || { echo "git requis"; exit 1; }
if ! command -v ffmpeg >/dev/null; then
  echo "⚠️ ffmpeg absent (recommandé pour rendu vidéo)"
fi

echo "[2/6] Création environnement virtuel (ou fallback système)"
USE_VENV=1
set +e
python3 -m venv .venv
VENV_RC=$?
set -e
if [[ $VENV_RC -ne 0 ]]; then
  USE_VENV=0
  echo "⚠️ venv indisponible (python3-venv manquant). On continue en mode système."
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[3/6] Installation stack fallback exécutable"
set +e
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install moviepy pysrt srt tqdm
PIP_RC=$?
set -e
if [[ $PIP_RC -ne 0 ]]; then
  echo "⚠️ Install pip partielle. La démo offline reste exécutable sans dépendances externes."
fi

echo "[4/6] Installation option sous-titres/traduction"
set +e
python3 -m pip install openai-whisper argostranslate
WHISPER_RC=$?
set -e
if [[ $WHISPER_RC -ne 0 ]]; then
  echo "⚠️ whisper/argostranslate non installés. Fallback SRT mock restera disponible."
fi

echo "[5/6] Tentative setup MoneyPrinterPlus (optionnel)"
if [[ ! -d external/MoneyPrinterPlus ]]; then
  mkdir -p external
  set +e
  git clone --depth 1 https://github.com/FujiwaraChoki/MoneyPrinterPlus.git external/MoneyPrinterPlus
  CLONE_RC=$?
  set -e
  if [[ $CLONE_RC -ne 0 ]]; then
    echo "⚠️ Clone MoneyPrinterPlus bloqué (réseau/accès). Fallback pipeline local prêt."
  fi
fi

if [[ -d external/MoneyPrinterPlus ]]; then
  echo "MoneyPrinterPlus cloné dans external/MoneyPrinterPlus"
fi

echo "[6/6] Terminé"
echo "Active l'env: source .venv/bin/activate"
echo "Lance la démo: ./run_demo.sh"
