# Content Factory v2

Pipeline autonome de production de vidéos short-form (TikTok, Reels, Shorts).

## Architecture

```
main.py           → Pipeline orchestrateur
├── config.py     → Configuration centralisée (.env)
├── script_gen.py → Génération de scripts via LLM (OpenAI/Anthropic/Groq)
├── tts.py        → Text-to-Speech (OpenAI TTS / ElevenLabs)
├── subtitles.py  → Sous-titres Whisper word-level → SRT + ASS
├── broll.py      → B-roll automatique (Pexels / Pixabay)
├── assembler.py  → Montage vidéo ffmpeg (clips + voix + subs + musique)
└── publisher.py  → Publication TikTok + Instagram
```

## Pipeline

```
Topic → [LLM Script] → [TTS Audio] → [Whisper Subs] → [B-Roll] → [FFmpeg Assembly] → Video.mp4
                                                                                         ↓
                                                                              [Publish TikTok/IG]
```

## Différences vs v1

| v1 (OpenClaw) | v2 |
|---|---|
| Script hardcodé en dur | LLM multi-provider (GPT-4o, Claude, Groq) |
| Pas de TTS | OpenAI TTS-HD + ElevenLabs |
| Sous-titres 3s fixes | Whisper word-level synchronisé |
| Pas de B-roll | Pexels/Pixabay API automatique |
| Écran noir = "vidéo" | FFmpeg pipeline complet |
| 0 publication | TikTok + Instagram API |
| Prompts ignorés | Prompts professionnels intégrés |

## Setup

```bash
cp .env.example .env
# Remplir les clés API dans .env
pip install -r requirements.txt
# ffmpeg requis : apt install ffmpeg

# Production unique
python main.py --topic "3 erreurs qui tuent ta visibilité locale" --niche "immobilier"

# Avec variantes A/B
python main.py --topic "..." --variants

# Mode batch (fichier texte, 1 topic/ligne)
python main.py --batch topics.txt --niche "horeca"

# Publication auto
python main.py --topic "..." --publish
```

## Prérequis

- Python 3.10+
- ffmpeg + ffprobe
- Clé API LLM (OpenAI, Anthropic, ou Groq)
- Clé API TTS (OpenAI ou ElevenLabs)
- Clé Pexels (gratuite) pour le B-roll
- Optionnel : tokens TikTok/Instagram pour publication auto

## Output

Chaque vidéo produit un dossier dans `outputs/` contenant :
- `script.json` + `script.txt` — Le script complet
- `voiceover.mp3` — Audio voix off
- `subtitles.srt` + `subtitles.ass` — Sous-titres synchronisés
- `broll/` — Clips vidéo stock
- `final_video.mp4` — Vidéo finale prête à publier
- `metadata.json` — Métadonnées complètes
- `variants.json` — Variantes A/B (si --variants)
