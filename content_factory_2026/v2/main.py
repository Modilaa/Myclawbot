"""
Content Factory v2 — Pipeline principal.

Usage:
    python main.py --topic "3 erreurs qui tuent ta visibilité locale"
    python main.py --topic "..." --niche "immobilier" --variants
    python main.py --topic "..." --publish
    python main.py --batch topics.txt --niche "horeca"
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

from config import ContentConfig
from script_gen import ScriptGenerator, VideoScript
from tts import TTSEngine
from subtitles import SubtitleGenerator
from broll import BRollProvider
from assembler import VideoAssembler
from publisher import Publisher


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


logger = logging.getLogger("content_factory")


class ContentFactory:
    """Pipeline complet de production de vidéos short-form."""

    def __init__(self, config: ContentConfig):
        self.config = config
        self.script_gen = ScriptGenerator(config.llm)
        self.tts = TTSEngine(config.tts)
        self.subtitles = SubtitleGenerator(config.subtitle)
        self.broll = BRollProvider(config.media)
        self.assembler = VideoAssembler(config)
        self.publisher = Publisher(config.publish)

    def produce(self, topic: str, niche: str = "business local",
                angle: str = "valeur actionnable",
                audience: str = "PME/indépendants",
                with_variants: bool = False,
                auto_publish: bool = False) -> dict:
        """
        Pipeline complet : Script → TTS → Subtitles → B-Roll → Video → (Publish)
        Retourne un dict avec les chemins de tous les artefacts.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = topic[:30].replace(" ", "_").lower()
        out_dir = os.path.join(self.config.output_dir, f"{slug}_{timestamp}")
        os.makedirs(out_dir, exist_ok=True)

        logger.info(f"=== Production démarrée: {topic[:60]} ===")
        logger.info(f"Output: {out_dir}")

        result = {"output_dir": out_dir, "artifacts": {}}

        # ── ÉTAPE 1 : Génération du script ──
        logger.info("📝 Étape 1/5 : Génération du script...")
        script = self.script_gen.generate(
            topic=topic, niche=niche, angle=angle,
            audience=audience, language=self.config.language,
        )

        # Sauvegarder le script
        script_path = os.path.join(out_dir, "script.json")
        with open(script_path, "w", encoding="utf-8") as f:
            json.dump({
                "hook": script.hook,
                "body": script.body,
                "cta": script.cta,
                "full_text": script.full_text,
                "title": script.title,
                "description": script.description,
                "hashtags": script.hashtags,
                "duration_estimate": script.duration_estimate_sec,
            }, f, ensure_ascii=False, indent=2)

        # Aussi en texte brut (pour lecture rapide)
        with open(os.path.join(out_dir, "script.txt"), "w", encoding="utf-8") as f:
            f.write(f"HOOK: {script.hook}\n\n")
            f.write(f"{script.body}\n\n")
            f.write(f"CTA: {script.cta}\n")

        result["artifacts"]["script"] = script_path
        logger.info(f"   Script: {script.duration_estimate_sec}s estimé, {len(script.full_text.split())} mots")

        # ── ÉTAPE 2 : Text-to-Speech ──
        logger.info("🎙️ Étape 2/5 : Génération audio (TTS)...")
        audio_path = os.path.join(out_dir, "voiceover.mp3")
        self.tts.generate(script.full_text, audio_path)

        audio_duration = TTSEngine.get_duration(audio_path)
        result["artifacts"]["audio"] = audio_path
        logger.info(f"   Audio: {audio_duration:.1f}s réels")

        # ── ÉTAPE 3 : Sous-titres (Whisper) ──
        logger.info("💬 Étape 3/5 : Sous-titres (Whisper word-level)...")
        sub_result = self.subtitles.generate(audio_path, out_dir)
        result["artifacts"]["subtitles"] = sub_result
        logger.info(f"   Sous-titres: {sub_result.get('word_count', 0)} mots, SRT + ASS")

        # ── ÉTAPE 4 : B-Roll ──
        logger.info("🎬 Étape 4/5 : Téléchargement B-roll...")
        visual_keywords = BRollProvider.extract_visual_keywords(script.full_text, niche)
        broll_dir = os.path.join(out_dir, "broll")
        clips = self.broll.get_clips(visual_keywords, broll_dir, count_per_keyword=2)
        result["artifacts"]["broll_clips"] = len(clips)
        logger.info(f"   B-roll: {len(clips)} clips téléchargés")

        # ── ÉTAPE 5 : Assemblage vidéo ──
        logger.info("🎞️ Étape 5/5 : Assemblage vidéo final...")
        bgm_path = VideoAssembler.find_bgm(self.config.media.bgm_dir)
        video_path = os.path.join(out_dir, "final_video.mp4")

        subtitle_ass = sub_result.get("ass", "")
        self.assembler.assemble(
            audio_path=audio_path,
            subtitle_ass_path=subtitle_ass,
            broll_clips=clips,
            output_path=video_path,
            bgm_path=bgm_path,
        )
        result["artifacts"]["video"] = video_path

        # ── MÉTADONNÉES ──
        metadata = {
            "topic": topic,
            "niche": niche,
            "angle": angle,
            "audience": audience,
            "language": self.config.language,
            "produced_at": datetime.now().isoformat(),
            "duration_sec": audio_duration,
            "title": script.title,
            "description": script.description,
            "hashtags": script.hashtags,
            "artifacts": {k: str(v) for k, v in result["artifacts"].items()},
        }
        metadata_path = os.path.join(out_dir, "metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        # ── VARIANTES (optionnel) ──
        if with_variants:
            logger.info("🔀 Génération de 3 variantes A/B...")
            variants = self.script_gen.generate_variants(script)
            variants_path = os.path.join(out_dir, "variants.json")
            with open(variants_path, "w", encoding="utf-8") as f:
                json.dump([{
                    "variant": v.variant,
                    "hook": v.hook,
                    "body": v.body,
                    "cta": v.cta,
                } for v in variants], f, ensure_ascii=False, indent=2)
            result["artifacts"]["variants"] = variants_path

        # ── PUBLICATION (optionnel) ──
        if auto_publish and self.config.publish.auto_publish:
            logger.info("📤 Publication...")
            pub_results = self.publisher.publish_all(
                video_path=video_path,
                title=script.title,
                description=script.description,
                hashtags=script.hashtags,
            )
            for pr in pub_results:
                status = "✅" if pr.success else "❌"
                logger.info(f"   {status} {pr.platform}: {pr.post_id or pr.error}")
            result["publish"] = [{"platform": p.platform, "success": p.success} for p in pub_results]

        logger.info(f"=== Production terminée: {out_dir} ===")
        return result


def main():
    parser = argparse.ArgumentParser(description="Content Factory v2 — Short-form video pipeline")
    parser.add_argument("--topic", type=str, help="Sujet de la vidéo")
    parser.add_argument("--batch", type=str, help="Fichier texte avec un topic par ligne")
    parser.add_argument("--niche", type=str, default="business local", help="Niche cible")
    parser.add_argument("--angle", type=str, default="valeur actionnable", help="Angle du contenu")
    parser.add_argument("--audience", type=str, default="PME/indépendants", help="Audience cible")
    parser.add_argument("--variants", action="store_true", help="Générer des variantes A/B")
    parser.add_argument("--publish", action="store_true", help="Publier automatiquement")
    parser.add_argument("--debug", action="store_true", help="Mode debug")
    args = parser.parse_args()

    setup_logging("DEBUG" if args.debug else "INFO")

    config = ContentConfig()
    factory = ContentFactory(config)

    if args.batch:
        # Mode batch : un topic par ligne
        with open(args.batch, "r", encoding="utf-8") as f:
            topics = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        logger.info(f"Mode batch: {len(topics)} vidéos à produire")
        for i, topic in enumerate(topics, 1):
            logger.info(f"\n{'='*60}\n[{i}/{len(topics)}] {topic}\n{'='*60}")
            try:
                factory.produce(
                    topic=topic, niche=args.niche, angle=args.angle,
                    audience=args.audience, with_variants=args.variants,
                    auto_publish=args.publish,
                )
            except Exception as e:
                logger.error(f"Échec production '{topic}': {e}")

    elif args.topic:
        factory.produce(
            topic=args.topic, niche=args.niche, angle=args.angle,
            audience=args.audience, with_variants=args.variants,
            auto_publish=args.publish,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
