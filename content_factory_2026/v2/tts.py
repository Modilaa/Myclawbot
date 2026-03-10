"""
Text-to-Speech — Multi-provider (OpenAI TTS, ElevenLabs).

Génère un fichier audio .mp3 à partir du texte du script.
L'audio est la source de vérité pour le timing des sous-titres.
"""

import os
import logging
from typing import Optional
from pathlib import Path

from config import TTSConfig

logger = logging.getLogger("content_factory")


class TTSEngine:
    """Génère de l'audio vocal à partir de texte."""

    def __init__(self, config: TTSConfig):
        self.config = config

    def generate(self, text: str, output_path: str,
                 voice: Optional[str] = None) -> str:
        """
        Génère un fichier audio à partir du texte.
        Retourne le chemin du fichier audio créé.
        """
        provider = self.config.provider.lower()

        if provider == "openai":
            return self._generate_openai(text, output_path, voice)
        elif provider == "elevenlabs":
            return self._generate_elevenlabs(text, output_path, voice)
        else:
            raise ValueError(f"TTS provider inconnu: {provider}")

    # ──────────────────────────────────────────
    # OpenAI TTS
    # ──────────────────────────────────────────

    def _generate_openai(self, text: str, output_path: str,
                         voice: Optional[str] = None) -> str:
        """Génère via OpenAI TTS (tts-1 ou tts-1-hd)."""
        from openai import OpenAI

        client = OpenAI(api_key=self.config.openai_key)
        voice_id = voice or self.config.openai_voice

        logger.info(f"TTS OpenAI: modèle={self.config.openai_model}, voix={voice_id}")

        # OpenAI TTS a une limite de 4096 caractères par appel
        # Pour les textes longs, on découpe et concatène
        chunks = self._split_text(text, max_chars=4000)

        if len(chunks) == 1:
            response = client.audio.speech.create(
                model=self.config.openai_model,
                voice=voice_id,
                input=text,
                response_format="mp3",
                speed=1.0,
            )
            response.stream_to_file(output_path)
        else:
            # Multi-chunk : générer puis concaténer avec ffmpeg
            temp_files = []
            for i, chunk in enumerate(chunks):
                temp_path = f"{output_path}.part{i}.mp3"
                response = client.audio.speech.create(
                    model=self.config.openai_model,
                    voice=voice_id,
                    input=chunk,
                    response_format="mp3",
                    speed=1.0,
                )
                response.stream_to_file(temp_path)
                temp_files.append(temp_path)

            self._concat_audio(temp_files, output_path)

            # Nettoyage
            for f in temp_files:
                os.remove(f)

        logger.info(f"Audio généré: {output_path}")
        return output_path

    # ──────────────────────────────────────────
    # ElevenLabs
    # ──────────────────────────────────────────

    def _generate_elevenlabs(self, text: str, output_path: str,
                              voice: Optional[str] = None) -> str:
        """Génère via ElevenLabs (qualité premium, meilleur en FR)."""
        import requests

        voice_id = voice or self.config.elevenlabs_voice_id
        if not voice_id:
            raise ValueError(
                "ELEVENLABS_VOICE_ID requis. "
                "Trouvez votre voice_id sur https://api.elevenlabs.io/v1/voices"
            )

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.config.elevenlabs_key,
        }

        payload = {
            "text": text,
            "model_id": self.config.elevenlabs_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.4,
                "use_speaker_boost": True,
            }
        }

        logger.info(f"TTS ElevenLabs: voice={voice_id}, model={self.config.elevenlabs_model}")

        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Audio généré: {output_path}")
        return output_path

    # ──────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────

    @staticmethod
    def _split_text(text: str, max_chars: int = 4000) -> list[str]:
        """Découpe le texte en chunks au niveau des phrases."""
        if len(text) <= max_chars:
            return [text]

        sentences = text.replace(".", ".\n").replace("!", "!\n").replace("?", "?\n").split("\n")
        chunks = []
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) + 1 > max_chars:
                if current:
                    chunks.append(current.strip())
                current = sentence
            else:
                current = f"{current} {sentence}" if current else sentence

        if current:
            chunks.append(current.strip())

        return chunks

    @staticmethod
    def _concat_audio(files: list[str], output: str):
        """Concatène plusieurs fichiers audio avec ffmpeg."""
        import subprocess

        list_file = f"{output}.list.txt"
        with open(list_file, "w") as f:
            for path in files:
                f.write(f"file '{path}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output
        ], check=True, capture_output=True)

        os.remove(list_file)

    @staticmethod
    def get_duration(audio_path: str) -> float:
        """Retourne la durée en secondes d'un fichier audio."""
        import subprocess
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ], capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
