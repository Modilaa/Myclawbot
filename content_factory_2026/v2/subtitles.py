"""
Sous-titres — Whisper word-level timing + formatage mobile-first.

Pipeline :
1. Audio → Whisper API (word-level timestamps)
2. Regroupement en segments lisibles (max 2 lignes, 32 chars/ligne)
3. Export SRT synchronisé avec l'audio réel
4. Export ASS avec style pour brûler dans la vidéo
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import SubtitleConfig

logger = logging.getLogger("content_factory")


@dataclass
class Word:
    text: str
    start: float  # secondes
    end: float


@dataclass
class SubtitleSegment:
    index: int
    start: float
    end: float
    text: str


class SubtitleGenerator:
    """Génère des sous-titres synchronisés via Whisper."""

    def __init__(self, config: SubtitleConfig):
        self.config = config

    def generate(self, audio_path: str, output_dir: str) -> dict:
        """
        Génère les sous-titres à partir de l'audio.
        Retourne les chemins des fichiers générés.
        """
        # 1. Transcription word-level via Whisper
        words = self._transcribe_words(audio_path)

        if not words:
            logger.warning("Whisper n'a retourné aucun mot — fallback texte")
            return {}

        # 2. Regroupement en segments lisibles
        segments = self._group_into_segments(words)

        # 3. Export SRT
        srt_path = os.path.join(output_dir, "subtitles.srt")
        self._export_srt(segments, srt_path)

        # 4. Export ASS (pour brûler avec ffmpeg)
        ass_path = os.path.join(output_dir, "subtitles.ass")
        self._export_ass(segments, ass_path)

        logger.info(f"Sous-titres: {len(segments)} segments, SRT + ASS générés")

        return {
            "srt": srt_path,
            "ass": ass_path,
            "segments": segments,
            "word_count": len(words),
        }

    # ──────────────────────────────────────────
    # Whisper transcription
    # ──────────────────────────────────────────

    def _transcribe_words(self, audio_path: str) -> list[Word]:
        """Transcription word-level via OpenAI Whisper API."""
        if self.config.mode == "api":
            return self._whisper_api(audio_path)
        else:
            return self._whisper_local(audio_path)

    def _whisper_api(self, audio_path: str) -> list[Word]:
        """OpenAI Whisper API avec timestamps word-level."""
        from openai import OpenAI

        client = OpenAI(api_key=self.config.openai_key)

        logger.info(f"Whisper API: transcription de {audio_path}")

        with open(audio_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model=self.config.model,
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["word"],
                language="fr",
            )

        words = []
        for w in response.words:
            words.append(Word(
                text=w.word.strip(),
                start=w.start,
                end=w.end,
            ))

        logger.info(f"Whisper: {len(words)} mots transcrits")
        return words

    def _whisper_local(self, audio_path: str) -> list[Word]:
        """Whisper local (nécessite whisper installé)."""
        import whisper

        model = whisper.load_model("base")
        result = model.transcribe(
            audio_path,
            language="fr",
            word_timestamps=True,
        )

        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append(Word(
                    text=w["word"].strip(),
                    start=w["start"],
                    end=w["end"],
                ))
        return words

    # ──────────────────────────────────────────
    # Regroupement en segments lisibles
    # ──────────────────────────────────────────

    def _group_into_segments(self, words: list[Word]) -> list[SubtitleSegment]:
        """
        Regroupe les mots en segments de sous-titres lisibles.
        Règles :
        - Max 2 lignes
        - Max 32 chars/ligne (optimisé mobile)
        - Coupe sur les fins de phrases quand possible
        - Durée min 0.8s, max 4s par segment
        """
        max_chars = self.config.max_chars_per_line * self.config.max_lines
        segments = []
        current_words: list[Word] = []
        current_text = ""

        for word in words:
            test_text = f"{current_text} {word.text}".strip() if current_text else word.text

            # Vérifier si on doit couper
            should_break = False

            # Limite de caractères
            if len(test_text) > max_chars:
                should_break = True

            # Limite de durée (4s max)
            if current_words and (word.end - current_words[0].start) > 4.0:
                should_break = True

            # Fin de phrase naturelle
            if current_text and current_text[-1] in ".!?":
                should_break = True

            if should_break and current_words:
                segments.append(SubtitleSegment(
                    index=len(segments) + 1,
                    start=current_words[0].start,
                    end=current_words[-1].end,
                    text=self._format_text(current_text),
                ))
                current_words = []
                current_text = ""

            current_words.append(word)
            current_text = f"{current_text} {word.text}".strip() if current_text else word.text

        # Dernier segment
        if current_words:
            segments.append(SubtitleSegment(
                index=len(segments) + 1,
                start=current_words[0].start,
                end=current_words[-1].end,
                text=self._format_text(current_text),
            ))

        return segments

    def _format_text(self, text: str) -> str:
        """Formate le texte pour lisibilité mobile (max 2 lignes)."""
        text = text.strip()
        max_per_line = self.config.max_chars_per_line

        if len(text) <= max_per_line:
            return text

        # Trouver le meilleur point de coupure
        words = text.split()
        line1 = ""
        line2_words = []
        for w in words:
            if len(f"{line1} {w}".strip()) <= max_per_line:
                line1 = f"{line1} {w}".strip()
            else:
                line2_words.append(w)

        if line2_words:
            line2 = " ".join(line2_words)
            if len(line2) > max_per_line:
                line2 = line2[:max_per_line - 1] + "…"
            return f"{line1}\n{line2}"

        return text

    # ──────────────────────────────────────────
    # Export SRT
    # ──────────────────────────────────────────

    def _export_srt(self, segments: list[SubtitleSegment], path: str):
        """Exporte en format SubRip (.srt)."""
        with open(path, "w", encoding="utf-8") as f:
            for seg in segments:
                f.write(f"{seg.index}\n")
                f.write(f"{self._srt_time(seg.start)} --> {self._srt_time(seg.end)}\n")
                f.write(f"{seg.text}\n\n")

    @staticmethod
    def _srt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    # ──────────────────────────────────────────
    # Export ASS (Advanced SubStation Alpha)
    # ──────────────────────────────────────────

    def _export_ass(self, segments: list[SubtitleSegment], path: str):
        """Exporte en format ASS pour brûler dans la vidéo avec ffmpeg."""
        cfg = self.config
        # Conversion couleur hex → ASS BGR (&H00BBGGRR)
        font_color = "&H00FFFFFF"  # blanc
        outline_color = "&H00000000"  # noir

        header = f"""[Script Info]
Title: Content Factory Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{cfg.font},{cfg.font_size},{font_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{cfg.outline_width},0,2,40,40,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(header)
            for seg in segments:
                start = self._ass_time(seg.start)
                end = self._ass_time(seg.end)
                # Remplacer les \n par \\N (newline ASS)
                text = seg.text.replace("\n", "\\N")
                f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    @staticmethod
    def _ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
