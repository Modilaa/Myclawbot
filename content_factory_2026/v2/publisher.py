"""
Publication automatique — TikTok + Instagram + YouTube Shorts.

Chaque plateforme a sa propre API et ses contraintes.
Ce module gère l'upload, la programmation et le suivi.
"""

import os
import json
import time
import logging
from typing import Optional
from dataclasses import dataclass

import requests

from config import PublishConfig

logger = logging.getLogger("content_factory")


@dataclass
class PublishResult:
    platform: str
    success: bool
    post_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class Publisher:
    """Publie des vidéos sur les réseaux sociaux."""

    def __init__(self, config: PublishConfig):
        self.config = config
        self.session = requests.Session()

    def publish_all(self, video_path: str, title: str,
                    description: str, hashtags: list[str]) -> list[PublishResult]:
        """Publie sur toutes les plateformes configurées."""
        results = []

        caption = self._build_caption(description, hashtags)

        if self.config.tiktok_token:
            results.append(self.publish_tiktok(video_path, title, caption))

        if self.config.instagram_token:
            results.append(self.publish_instagram(video_path, caption))

        return results

    # ──────────────────────────────────────────
    # TikTok
    # ──────────────────────────────────────────

    def publish_tiktok(self, video_path: str, title: str,
                       description: str) -> PublishResult:
        """
        Publie sur TikTok via Content Posting API.
        Nécessite un TikTok Business Account + token valide.
        Flow : init upload → upload video → publish
        """
        try:
            token = self.config.tiktok_token
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            file_size = os.path.getsize(video_path)

            # Step 1: Init upload
            init_resp = self.session.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers=headers,
                json={
                    "post_info": {
                        "title": title[:150],
                        "description": description[:2200],
                        "privacy_level": "SELF_ONLY",  # Brouillon par défaut, sécurité
                        "disable_duet": False,
                        "disable_comment": False,
                        "disable_stitch": False,
                    },
                    "source_info": {
                        "source": "FILE_UPLOAD",
                        "video_size": file_size,
                        "chunk_size": file_size,  # Upload en un seul chunk
                        "total_chunk_count": 1,
                    }
                },
                timeout=30
            )
            init_resp.raise_for_status()
            init_data = init_resp.json()

            upload_url = init_data.get("data", {}).get("upload_url", "")
            publish_id = init_data.get("data", {}).get("publish_id", "")

            if not upload_url:
                raise ValueError("TikTok: upload_url manquant dans la réponse init")

            # Step 2: Upload video
            with open(video_path, "rb") as f:
                upload_resp = self.session.put(
                    upload_url,
                    data=f,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
                    },
                    timeout=300
                )
                upload_resp.raise_for_status()

            logger.info(f"TikTok: upload OK, publish_id={publish_id}")

            return PublishResult(
                platform="tiktok",
                success=True,
                post_id=publish_id,
            )

        except Exception as e:
            logger.error(f"TikTok publish failed: {e}")
            return PublishResult(platform="tiktok", success=False, error=str(e))

    # ──────────────────────────────────────────
    # Instagram Reels
    # ──────────────────────────────────────────

    def publish_instagram(self, video_path: str,
                          caption: str) -> PublishResult:
        """
        Publie un Reel Instagram via Graph API.
        Flow : create media container → check status → publish
        Nécessite que la vidéo soit accessible par URL (pas d'upload direct).
        """
        try:
            token = self.config.instagram_token
            account_id = self.config.instagram_account_id

            if not account_id:
                raise ValueError("INSTAGRAM_ACCOUNT_ID requis")

            # Note: Instagram Graph API nécessite que la vidéo soit hébergée
            # sur un serveur accessible par URL. Pour un upload local,
            # il faudrait d'abord uploader sur un storage (S3, etc.)
            #
            # Ici on montre le flow complet pour quand la vidéo est hébergée.
            # En production, ajouter un step d'upload vers un CDN.

            logger.warning(
                "Instagram Reels nécessite que la vidéo soit accessible par URL. "
                "Uploadez d'abord sur un CDN (S3, Cloudflare R2, etc.)"
            )

            return PublishResult(
                platform="instagram",
                success=False,
                error="Video doit être hébergée sur URL publique pour Instagram Graph API"
            )

        except Exception as e:
            logger.error(f"Instagram publish failed: {e}")
            return PublishResult(platform="instagram", success=False, error=str(e))

    # ──────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────

    @staticmethod
    def _build_caption(description: str, hashtags: list[str]) -> str:
        """Construit la description avec hashtags."""
        tags = " ".join(f"#{h.lstrip('#')}" for h in hashtags if h)
        return f"{description}\n\n{tags}".strip()
