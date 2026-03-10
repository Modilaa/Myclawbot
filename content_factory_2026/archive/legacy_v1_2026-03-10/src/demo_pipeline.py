#!/usr/bin/env python3
"""Mini local demo pipeline for short-form content factory.
No secrets required. Produces script, subtitles, translation fallback, and metadata.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path


def split_sentences(text: str) -> list[str]:
    chunks = [c.strip() for c in text.replace("\n", " ").split(".")]
    return [c + "." for c in chunks if c]


def to_srt(lines: list[str], sec_per_line: int = 3) -> str:
    out = []
    for i, line in enumerate(lines, start=1):
        start = (i - 1) * sec_per_line
        end = i * sec_per_line
        out.append(str(i))
        out.append(f"00:00:{start:02d},000 --> 00:00:{end:02d},000")
        out.append(line)
        out.append("")
    return "\n".join(out)


def fake_translate_fr(lines: list[str]) -> list[str]:
    return [f"[FR] {line}" for line in lines]


def ffmpeg_color_video(path: Path, duration: int = 12) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1080x1920:d={duration}",
        "-vf",
        "drawtext=text='Content Factory 2026 Demo':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
        str(path),
    ]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path.exists()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="3 erreurs qui ruinent ton acquisition client locale")
    parser.add_argument("--out", default="outputs")
    args = parser.parse_args()

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.out) / f"demo_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    script = (
        f"Hook: Tu veux plus de clients en 2026 ? Voici 3 erreurs fatales. "
        f"Sujet: {args.topic}. "
        "Erreur 1: publier sans hook concret. "
        "Erreur 2: vidéos trop longues sans sous-titres. "
        "Erreur 3: aucun call-to-action clair. "
        "CTA: Commente START pour recevoir le plan complet."
    )

    lines = split_sentences(script)
    srt = to_srt(lines)
    srt_fr = to_srt(fake_translate_fr(lines))

    (run_dir / "script.txt").write_text(script, encoding="utf-8")
    (run_dir / "subtitles_en.srt").write_text(srt, encoding="utf-8")
    (run_dir / "subtitles_fr.srt").write_text(srt_fr, encoding="utf-8")

    video_ok = ffmpeg_color_video(run_dir / "demo_video.mp4", duration=max(9, len(lines) * 3))

    metadata = {
        "created_at": dt.datetime.now().isoformat(),
        "topic": args.topic,
        "artifacts": ["script.txt", "subtitles_en.srt", "subtitles_fr.srt"] + (["demo_video.mp4"] if video_ok else []),
        "note": "Demo offline sans API. Utiliser MoneyPrinterPlus/Whisper pour production réelle.",
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Demo generated: {run_dir}")
    if not video_ok:
        print("⚠️ ffmpeg absent: demo_video.mp4 non générée")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
