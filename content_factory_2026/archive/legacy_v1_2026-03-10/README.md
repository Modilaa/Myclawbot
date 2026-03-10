# Content Factory 2026 (indépendant d'Automaly)

Stack local reproductible pour produire du short-form, avec fallback sans API.

## Objectif
- Générer un script court orienté hook/CTA
- Produire des sous-titres `.srt`
- Préparer une piste traduction
- Générer un artefact vidéo démo local (si `ffmpeg` présent)

## Architecture
- `scripts/bootstrap.sh` → setup global + tentative MoneyPrinterPlus
- `run_demo.sh` → exécute un mini flux offline (sans secrets)
- `src/demo_pipeline.py` → pipeline local de démonstration
- `scripts/bootstrap_comfyui.sh` → track premium ComfyUI (optionnel)

## Setup pas-à-pas
```bash
cd /data/.openclaw/workspace/content_factory_2026
chmod +x scripts/*.sh run_demo.sh
./scripts/bootstrap.sh
./run_demo.sh
```

## Résultat attendu
Dans `outputs/demo_YYYYmmdd_HHMMSS/` :
- `script.txt`
- `subtitles_en.srt`
- `subtitles_fr.srt`
- `metadata.json`
- `demo_video.mp4` (si ffmpeg dispo)

## MoneyPrinterPlus
`bootstrap.sh` tente de cloner :
- `external/MoneyPrinterPlus`

Si clone/installation bloquée, le fallback local reste **fonctionnel** (démo + structure prod).

## Pipeline sous-titres/traduction
- Option primaire: `openai-whisper` + `argostranslate`
- Fallback: génération SRT locale de démonstration

## Track premium: ComfyUI wrappers
```bash
./scripts/bootstrap_comfyui.sh
```
Puis lancer ComfyUI:
```bash
cd external/ComfyUI
source .venv/bin/activate
python main.py --listen 127.0.0.1 --port 8188
```

## Comptes nécessaires (à demander à Justin)
1. **TikTok Business / Creator** + token API publication
2. **Meta Developers**: App + permissions Instagram Graph + Facebook Pages
3. **Compte Instagram Pro** lié à une Page Facebook
4. **Page Facebook** (token long-lived)
5. **Option YouTube**: projet Google Cloud + YouTube Data API v3
6. **Provider TTS** (ElevenLabs ou Azure Speech)
7. **Provider LLM** (OpenAI/Anthropic/Groq)
8. **Banque médias stock** (Pexels/Pixabay API)

## Sécurité
- Aucun secret versionné
- Utiliser `.env` local basé sur `.env.example`
