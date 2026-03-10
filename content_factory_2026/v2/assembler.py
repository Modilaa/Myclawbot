"""
Assembleur vidéo — Pipeline ffmpeg pour le montage final.

Pipeline :
1. Préparer les clips B-roll (resize, durée)
2. Concaténer les clips pour couvrir la durée de l'audio
3. Ajouter la voix off (audio TTS)
4. Brûler les sous-titres (ASS)
5. Ajouter la musique de fond
6. Export final en 1080x1920 / 30fps / H.264
"""

import os
import subprocess
import logging
import random
from typing import Optional
from pathlib import Path

from config import ContentConfig

logger = logging.getLogger("content_factory")


class VideoAssembler:
    """Assemble la vidéo finale à partir des composants."""

    def __init__(self, config: ContentConfig):
        self.config = config
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """Vérifie que ffmpeg est disponible."""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        except FileNotFoundError:
            raise RuntimeError(
                "ffmpeg non trouvé. Installez-le : apt install ffmpeg (Linux) "
                "ou brew install ffmpeg (Mac)"
            )

    def assemble(self, audio_path: str, subtitle_ass_path: str,
                 broll_clips: list, output_path: str,
                 bgm_path: Optional[str] = None) -> str:
        """
        Assemble la vidéo finale.
        1. Clips B-roll → vidéo de fond
        2. + Audio voix off
        3. + Sous-titres brûlés
        4. + Musique de fond
        """
        work_dir = os.path.dirname(output_path)
        os.makedirs(work_dir, exist_ok=True)

        # Durée de l'audio (source de vérité)
        audio_duration = self._get_duration(audio_path)
        logger.info(f"Durée audio: {audio_duration:.1f}s")

        # 1. Préparer la vidéo de fond (B-roll concaténé)
        bg_video = os.path.join(work_dir, "_bg_video.mp4")
        self._build_background_video(broll_clips, bg_video, audio_duration)

        # 2. Combiner : vidéo + voix off + sous-titres + musique
        self._final_mix(
            bg_video, audio_path, subtitle_ass_path,
            bgm_path, output_path, audio_duration
        )

        # Nettoyage
        for temp in [bg_video]:
            if os.path.exists(temp):
                os.remove(temp)

        size_mb = os.path.getsize(output_path) / 1024 / 1024
        logger.info(f"Vidéo finale: {output_path} ({size_mb:.1f} MB)")
        return output_path

    # ──────────────────────────────────────────
    # Background video (B-roll)
    # ──────────────────────────────────────────

    def _build_background_video(self, clips: list, output: str, target_duration: float):
        """
        Construit la vidéo de fond en concaténant les clips B-roll.
        Chaque clip est redimensionné en 1080x1920 (vertical).
        Si pas assez de B-roll, on boucle.
        """
        w = self.config.output_width
        h = self.config.output_height

        if not clips:
            # Fallback : fond noir
            logger.warning("Pas de B-roll — génération fond avec gradient")
            self._generate_gradient_background(output, target_duration)
            return

        # Préparer chaque clip
        prepared = []
        for i, clip in enumerate(clips):
            temp = os.path.join(os.path.dirname(output), f"_clip_{i}.mp4")
            self._prepare_clip(clip.path, temp, w, h)
            prepared.append(temp)

        # Calculer la durée totale disponible
        total_duration = sum(self._get_duration(p) for p in prepared)

        # Si pas assez, boucler les clips
        if total_duration < target_duration:
            ratio = int(target_duration / total_duration) + 1
            prepared = (prepared * ratio)[:20]  # Max 20 clips

        # Concaténer
        self._concat_clips(prepared, output, target_duration)

        # Nettoyage
        for p in prepared:
            if os.path.exists(p) and p != output:
                os.remove(p)

    def _prepare_clip(self, input_path: str, output_path: str, w: int, h: int):
        """Redimensionne un clip en format vertical avec crop/pad."""
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},"
                "setsar=1"
            ),
            "-c:v", "libx264", "-preset", "fast",
            "-crf", "23", "-an",  # Pas d'audio
            "-r", str(self.config.fps),
            "-pix_fmt", "yuv420p",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    def _concat_clips(self, clips: list[str], output: str, max_duration: float):
        """Concatène les clips avec un fichier de liste ffmpeg."""
        list_file = f"{output}.list.txt"
        with open(list_file, "w") as f:
            for path in clips:
                f.write(f"file '{os.path.abspath(path)}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-t", str(max_duration),
            "-c:v", "libx264", "-preset", "fast",
            "-crf", "23", "-an",
            "-r", str(self.config.fps),
            "-pix_fmt", "yuv420p",
            output
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        os.remove(list_file)

    def _generate_gradient_background(self, output: str, duration: float):
        """Génère un fond dégradé animé quand il n'y a pas de B-roll."""
        w = self.config.output_width
        h = self.config.output_height
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i",
            f"gradients=s={w}x{h}:c0=#1a1a2e:c1=#16213e:d={duration}:speed=0.5:type=linear",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast",
            "-crf", "23",
            "-r", str(self.config.fps),
            "-pix_fmt", "yuv420p",
            output
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            # Fallback encore plus simple : couleur unie
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i",
                f"color=c=#1a1a2e:s={w}x{h}:d={duration}:r={self.config.fps}",
                "-c:v", "libx264", "-preset", "fast",
                "-crf", "23", "-pix_fmt", "yuv420p",
                output
            ]
            subprocess.run(cmd, capture_output=True, check=True)

    # ──────────────────────────────────────────
    # Mix final
    # ──────────────────────────────────────────

    def _final_mix(self, video_path: str, voice_path: str,
                   subtitle_ass: str, bgm_path: Optional[str],
                   output_path: str, duration: float):
        """
        Mix final : vidéo + voix + sous-titres + musique.
        Utilise un filtre complexe ffmpeg.
        """
        inputs = ["-i", video_path, "-i", voice_path]
        filter_parts = []
        audio_inputs = ["[1:a]"]  # Voix off

        # Musique de fond (optionnelle)
        if bgm_path and os.path.exists(bgm_path):
            inputs.extend(["-stream_loop", "-1", "-i", bgm_path])
            bgm_volume = self.config.media.bgm_volume
            filter_parts.append(
                f"[2:a]atrim=0:{duration},volume={bgm_volume},afade=t=out:st={duration-2}:d=2[bgm]"
            )
            audio_inputs.append("[bgm]")

        # Sous-titres brûlés
        sub_filter = f"ass='{subtitle_ass}'" if os.path.exists(subtitle_ass) else ""

        # Construire le filtre
        if sub_filter:
            filter_parts.append(f"[0:v]{sub_filter}[vout]")
            video_map = "[vout]"
        else:
            video_map = "0:v"

        # Mix audio
        if len(audio_inputs) > 1:
            filter_parts.append(
                f"{''.join(audio_inputs)}amix=inputs={len(audio_inputs)}:normalize=0[aout]"
            )
            audio_map = "[aout]"
        else:
            audio_map = "1:a"

        cmd = ["ffmpeg", "-y"] + inputs

        if filter_parts:
            cmd.extend(["-filter_complex", ";".join(filter_parts)])

        cmd.extend([
            "-map", video_map,
            "-map", audio_map,
            "-c:v", "libx264", "-preset", "medium",
            "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-r", str(self.config.fps),
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-movflags", "+faststart",  # Streaming-friendly
            output_path
        ])

        logger.info("Assemblage final ffmpeg...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"ffmpeg error: {result.stderr[-500:]}")
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-200:]}")

    # ──────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────

    @staticmethod
    def _get_duration(path: str) -> float:
        result = subprocess.run([
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ], capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    @staticmethod
    def find_bgm(bgm_dir: str) -> Optional[str]:
        """Trouve un fichier de musique de fond au hasard."""
        if not os.path.isdir(bgm_dir):
            return None
        bgm_files = [
            os.path.join(bgm_dir, f)
            for f in os.listdir(bgm_dir)
            if f.endswith((".mp3", ".m4a", ".wav", ".ogg"))
        ]
        return random.choice(bgm_files) if bgm_files else None
