"""
B-Roll — Téléchargement automatique de clips vidéo stock.

Sources :
- Pexels Video API (gratuit, haute qualité, pas de watermark)
- Pixabay Video API (gratuit, fallback)

Stratégie :
1. Extraire les mots-clés visuels du script
2. Chercher des clips pertinents (vertical preferred)
3. Télécharger et préparer pour le montage
"""

import os
import re
import logging
from typing import Optional
from dataclasses import dataclass
from pathlib import Path

import requests

from config import MediaConfig

logger = logging.getLogger("content_factory")


@dataclass
class VideoClip:
    """Un clip vidéo B-roll téléchargé."""
    path: str
    duration: float
    width: int
    height: int
    keyword: str
    source: str  # "pexels", "pixabay"


class BRollProvider:
    """Fournit des clips B-roll depuis des banques vidéo stock."""

    def __init__(self, config: MediaConfig):
        self.config = config
        self.session = requests.Session()

    def get_clips(self, keywords: list[str], output_dir: str,
                  count_per_keyword: int = 2,
                  prefer_vertical: bool = True) -> list[VideoClip]:
        """
        Télécharge des clips B-roll pour les mots-clés donnés.
        Retourne la liste des clips téléchargés.
        """
        os.makedirs(output_dir, exist_ok=True)
        clips = []

        for kw in keywords:
            try:
                new_clips = self._search_and_download(
                    kw, output_dir, count_per_keyword, prefer_vertical
                )
                clips.extend(new_clips)
            except Exception as e:
                logger.warning(f"B-roll '{kw}' failed: {e}")

        logger.info(f"B-roll: {len(clips)} clips téléchargés pour {len(keywords)} mots-clés")
        return clips

    def _search_and_download(self, keyword: str, output_dir: str,
                              count: int, prefer_vertical: bool) -> list[VideoClip]:
        """Cherche et télécharge des clips pour un mot-clé."""
        clips = []

        # Essayer Pexels d'abord
        if self.config.pexels_key:
            clips = self._pexels_search(keyword, output_dir, count, prefer_vertical)
            if clips:
                return clips

        # Fallback Pixabay
        if self.config.pixabay_key:
            clips = self._pixabay_search(keyword, output_dir, count, prefer_vertical)

        return clips

    # ──────────────────────────────────────────
    # Pexels Video API
    # ──────────────────────────────────────────

    def _pexels_search(self, keyword: str, output_dir: str,
                        count: int, prefer_vertical: bool) -> list[VideoClip]:
        """Recherche et télécharge depuis Pexels."""
        headers = {"Authorization": self.config.pexels_key}

        params = {
            "query": keyword,
            "per_page": count * 3,  # Prendre plus pour filtrer
            "orientation": "portrait" if prefer_vertical else "landscape",
        }

        resp = self.session.get(
            "https://api.pexels.com/videos/search",
            headers=headers, params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        clips = []
        for video in data.get("videos", [])[:count]:
            try:
                clip = self._download_pexels_video(video, keyword, output_dir, prefer_vertical)
                if clip:
                    clips.append(clip)
            except Exception as e:
                logger.debug(f"Pexels download failed: {e}")

        return clips

    def _download_pexels_video(self, video: dict, keyword: str,
                                output_dir: str, prefer_vertical: bool) -> Optional[VideoClip]:
        """Télécharge le meilleur fichier vidéo Pexels."""
        files = video.get("video_files", [])
        if not files:
            return None

        # Trier : préférer vertical, HD, mp4
        def score_file(f):
            w = f.get("width", 0)
            h = f.get("height", 0)
            is_vertical = h > w
            is_hd = min(w, h) >= 720
            is_mp4 = f.get("file_type", "") == "video/mp4"
            # Score : vertical match + résolution + format
            return (
                (10 if is_vertical == prefer_vertical else 0) +
                (5 if is_hd else 0) +
                (3 if is_mp4 else 0) +
                min(w, h) / 1000  # Préférer meilleure résolution
            )

        files.sort(key=score_file, reverse=True)
        best = files[0]

        # Télécharger
        url = best.get("link", "")
        if not url:
            return None

        video_id = video.get("id", "unknown")
        filename = f"broll_{keyword.replace(' ', '_')}_{video_id}.mp4"
        filepath = os.path.join(output_dir, filename)

        resp = self.session.get(url, stream=True, timeout=60)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return VideoClip(
            path=filepath,
            duration=video.get("duration", 0),
            width=best.get("width", 0),
            height=best.get("height", 0),
            keyword=keyword,
            source="pexels",
        )

    # ──────────────────────────────────────────
    # Pixabay Video API
    # ──────────────────────────────────────────

    def _pixabay_search(self, keyword: str, output_dir: str,
                         count: int, prefer_vertical: bool) -> list[VideoClip]:
        """Recherche et télécharge depuis Pixabay."""
        params = {
            "key": self.config.pixabay_key,
            "q": keyword,
            "video_type": "film",
            "per_page": count * 2,
        }

        resp = self.session.get(
            "https://pixabay.com/api/videos/",
            params=params, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        clips = []
        for hit in data.get("hits", [])[:count]:
            try:
                videos = hit.get("videos", {})
                # Préférer "medium" (720p) ou "small" (360p)
                variant = videos.get("medium") or videos.get("small") or {}
                url = variant.get("url", "")
                if not url:
                    continue

                video_id = hit.get("id", "unknown")
                filename = f"broll_{keyword.replace(' ', '_')}_{video_id}.mp4"
                filepath = os.path.join(output_dir, filename)

                resp = self.session.get(url, stream=True, timeout=60)
                resp.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                clips.append(VideoClip(
                    path=filepath,
                    duration=hit.get("duration", 0),
                    width=variant.get("width", 0),
                    height=variant.get("height", 0),
                    keyword=keyword,
                    source="pixabay",
                ))
            except Exception as e:
                logger.debug(f"Pixabay download failed: {e}")

        return clips

    # ──────────────────────────────────────────
    # Extraction de mots-clés visuels
    # ──────────────────────────────────────────

    @staticmethod
    def extract_visual_keywords(script_text: str, niche: str = "") -> list[str]:
        """
        Extrait des mots-clés visuels depuis le script pour la recherche B-roll.
        Ex: "3 erreurs qui font perdre des clients" → ["business meeting", "clients", "erreur"]
        """
        # Mots-clés thématiques par niche
        niche_keywords = {
            "immobilier": ["real estate", "house", "property", "apartment"],
            "restaurant": ["restaurant", "food", "cooking", "chef"],
            "artisan": ["craftsman", "workshop", "tools", "repair"],
            "ecommerce": ["online shopping", "product", "packaging", "delivery"],
            "business": ["office", "meeting", "business", "teamwork"],
        }

        keywords = []

        # Ajouter les mots-clés de la niche
        for key, values in niche_keywords.items():
            if key in niche.lower():
                keywords.extend(values[:2])
                break

        # Mots visuels génériques utiles pour le short-form
        generic = ["success", "growth", "professional", "technology"]

        if not keywords:
            keywords = generic[:2]

        # Garder 4-6 mots-clés max
        return keywords[:6]
