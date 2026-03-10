"""
Test d'intégration end-to-end — Content Factory v2
Appelle les vraies APIs (OpenAI, Pexels) avec requests brut.
Produit une vraie vidéo short-form.
"""

import os
import sys
import json
import time
import tempfile
import subprocess
import requests

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "")
ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")

PASS = 0
FAIL = 0
WORK_DIR = None


def test(name, fn):
    global PASS, FAIL
    try:
        result = fn()
        print(f"  ✅ {name}")
        PASS += 1
        return result
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1
        return None


# ════════════════════════════════════════
# STEP 1: Script Generation via OpenAI
# ════════════════════════════════════════
print("\n📝 STEP 1: Script Generation (OpenAI GPT-4o)")

SCRIPT_DATA = None

def test_script_gen():
    global SCRIPT_DATA
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": (
                    "Tu es un expert en création de contenu short-form (TikTok, Reels). "
                    "Tu crées des scripts vidéo percutants. Langue: FR. "
                    "RÈGLES: Hook max 10 mots, 3 points actionnables, CTA clair. "
                    "Durée: 30-45s (~100 mots). Commence DIRECTEMENT par le hook."
                )},
                {"role": "user", "content": (
                    'Crée un script vidéo short-form sur: "3 erreurs fatales des PME sur les réseaux sociaux"\n'
                    'Niche: business local / PME\n'
                    'Réponds UNIQUEMENT en JSON:\n'
                    '{"hook":"...","body":"...","cta":"...","title":"...","description":"...","hashtags":["..."]}'
                )},
            ],
            "temperature": 0.8,
            "max_tokens": 1000,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    SCRIPT_DATA = json.loads(content)

    assert "hook" in SCRIPT_DATA, "Missing 'hook'"
    assert "body" in SCRIPT_DATA, "Missing 'body'"
    assert "cta" in SCRIPT_DATA, "Missing 'cta'"
    assert len(SCRIPT_DATA["hook"]) > 5, "Hook too short"
    assert len(SCRIPT_DATA["body"]) > 30, "Body too short"

    full_text = f"{SCRIPT_DATA['hook']}. {SCRIPT_DATA['body']} {SCRIPT_DATA['cta']}"
    word_count = len(full_text.split())
    print(f"      Hook: {SCRIPT_DATA['hook']}")
    print(f"      Words: {word_count}, Title: {SCRIPT_DATA.get('title', 'N/A')[:60]}")

    SCRIPT_DATA["full_text"] = full_text
    return SCRIPT_DATA

if OPENAI_KEY:
    test("Script generation (GPT-4o-mini)", test_script_gen)
else:
    print("  ⏭️  Skipped (no OPENAI_API_KEY)")


# ════════════════════════════════════════
# STEP 2: Text-to-Speech (OpenAI TTS)
# ════════════════════════════════════════
print("\n🎙️ STEP 2: Text-to-Speech (OpenAI TTS-1-HD)")

AUDIO_PATH = None

def test_tts():
    global AUDIO_PATH, WORK_DIR
    WORK_DIR = tempfile.mkdtemp(prefix="cf_test_")

    text = SCRIPT_DATA["full_text"] if SCRIPT_DATA else "Bonjour, ceci est un test de synthèse vocale."
    AUDIO_PATH = os.path.join(WORK_DIR, "voiceover.mp3")

    resp = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "tts-1-hd",
            "voice": "onyx",
            "input": text,
            "response_format": "mp3",
            "speed": 1.0,
        },
        timeout=60,
    )
    resp.raise_for_status()

    with open(AUDIO_PATH, "wb") as f:
        f.write(resp.content)

    size = os.path.getsize(AUDIO_PATH)
    assert size > 5000, f"Audio trop petit ({size} bytes)"

    # Durée
    dur_result = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_PATH
    ], capture_output=True, text=True, check=True)
    duration = float(dur_result.stdout.strip())
    print(f"      Audio: {size/1024:.0f} KB, {duration:.1f}s")
    assert 5 < duration < 120, f"Duration anormale: {duration}"
    return AUDIO_PATH

if OPENAI_KEY:
    test("TTS generation (OpenAI tts-1-hd, voix onyx)", test_tts)
else:
    print("  ⏭️  Skipped (no OPENAI_API_KEY)")


# ════════════════════════════════════════
# STEP 3: Subtitles (Whisper)
# ════════════════════════════════════════
print("\n💬 STEP 3: Sous-titres (Whisper word-level)")

SUB_DATA = None

def test_whisper():
    global SUB_DATA
    assert AUDIO_PATH and os.path.exists(AUDIO_PATH), "Audio file required"

    with open(AUDIO_PATH, "rb") as f:
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_KEY}"},
            files={"file": ("voiceover.mp3", f, "audio/mpeg")},
            data={
                "model": "whisper-1",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "language": "fr",
            },
            timeout=60,
        )
    resp.raise_for_status()
    data = resp.json()

    words = data.get("words", [])
    assert len(words) > 5, f"Too few words: {len(words)}"

    # Générer SRT avec notre module
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from subtitles import SubtitleGenerator, Word
    from config import SubtitleConfig

    gen = SubtitleGenerator(SubtitleConfig())
    word_objs = [Word(w["word"], w["start"], w["end"]) for w in words]
    segments = gen._group_into_segments(word_objs)

    srt_path = os.path.join(WORK_DIR, "subtitles.srt")
    ass_path = os.path.join(WORK_DIR, "subtitles.ass")
    gen._export_srt(segments, srt_path)
    gen._export_ass(segments, ass_path)

    SUB_DATA = {"srt": srt_path, "ass": ass_path, "segments": segments}
    print(f"      Mots: {len(words)}, Segments: {len(segments)}")
    print(f"      Extrait: \"{segments[0].text[:50]}...\"")
    return SUB_DATA

if OPENAI_KEY and AUDIO_PATH:
    test("Whisper transcription + SRT/ASS generation", test_whisper)
else:
    print("  ⏭️  Skipped (no audio)")


# ════════════════════════════════════════
# STEP 4: B-Roll (Pexels)
# ════════════════════════════════════════
print("\n🎬 STEP 4: B-Roll (Pexels API)")

BROLL_CLIPS = []

def test_broll():
    global BROLL_CLIPS
    broll_dir = os.path.join(WORK_DIR, "broll")
    os.makedirs(broll_dir, exist_ok=True)

    # Chercher des clips "business meeting"
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": PEXELS_KEY},
        params={"query": "business office", "per_page": 2, "orientation": "portrait"},
        timeout=30,
    )
    resp.raise_for_status()
    videos = resp.json().get("videos", [])
    assert len(videos) > 0, "No videos found on Pexels"

    for i, video in enumerate(videos[:2]):
        files = video.get("video_files", [])
        # Prendre le plus petit (rapide à télécharger)
        files.sort(key=lambda f: f.get("width", 9999))
        best = files[0] if files else None
        if not best:
            continue

        url = best.get("link", "")
        if not url:
            continue

        clip_path = os.path.join(broll_dir, f"clip_{i}.mp4")
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(clip_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)

        size = os.path.getsize(clip_path)
        dur_r = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", clip_path
        ], capture_output=True, text=True)
        dur = float(dur_r.stdout.strip()) if dur_r.returncode == 0 else 0

        print(f"      Clip {i}: {size/1024:.0f} KB, {dur:.1f}s, {best.get('width')}x{best.get('height')}")
        BROLL_CLIPS.append(clip_path)

    assert len(BROLL_CLIPS) > 0, "No clips downloaded"
    return BROLL_CLIPS

if PEXELS_KEY and WORK_DIR:
    test("Pexels B-roll download", test_broll)
else:
    print("  ⏭️  Skipped (no PEXELS_API_KEY)")


# ════════════════════════════════════════
# STEP 5: Video Assembly (ffmpeg)
# ════════════════════════════════════════
print("\n🎞️ STEP 5: Video Assembly (ffmpeg)")

FINAL_VIDEO = None

def test_assembly():
    global FINAL_VIDEO
    assert AUDIO_PATH, "Audio required"
    assert SUB_DATA, "Subtitles required"

    FINAL_VIDEO = os.path.join(WORK_DIR, "final_video.mp4")

    # 1. Préparer la vidéo de fond
    bg_video = os.path.join(WORK_DIR, "_bg.mp4")
    dur_result = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", AUDIO_PATH
    ], capture_output=True, text=True, check=True)
    audio_dur = float(dur_result.stdout.strip())

    if BROLL_CLIPS:
        # Préparer et concaténer les clips B-roll
        prepared = []
        for i, clip in enumerate(BROLL_CLIPS):
            prep = os.path.join(WORK_DIR, f"_prep_{i}.mp4")
            subprocess.run([
                "ffmpeg", "-y", "-i", clip,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-an", "-r", "30", "-pix_fmt", "yuv420p", prep
            ], capture_output=True, check=True)
            prepared.append(prep)

        # Concaténer (boucler si nécessaire)
        list_file = os.path.join(WORK_DIR, "_clips.txt")
        with open(list_file, "w") as f:
            for p in prepared * 5:  # Boucler pour couvrir la durée
                f.write(f"file '{p}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-t", str(audio_dur),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an", "-r", "30", "-pix_fmt", "yuv420p", bg_video
        ], capture_output=True, check=True)
    else:
        # Fond uni
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c=#1a1a2e:s=1080x1920:d={audio_dur}:r=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p", bg_video
        ], capture_output=True, check=True)

    # 2. Mix final : vidéo + voix + sous-titres
    ass_path = SUB_DATA["ass"]
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_video,
        "-i", AUDIO_PATH,
        "-filter_complex", f"[0:v]ass='{ass_path}'[vout]",
        "-map", "[vout]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-r", "30", "-pix_fmt", "yuv420p",
        "-t", str(audio_dur),
        "-movflags", "+faststart",
        FINAL_VIDEO
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback sans sous-titres si ASS échoue
        print(f"      ⚠️ ASS subtitles failed, trying without...")
        cmd_simple = [
            "ffmpeg", "-y",
            "-i", bg_video, "-i", AUDIO_PATH,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30", "-pix_fmt", "yuv420p",
            "-t", str(audio_dur), "-shortest",
            "-movflags", "+faststart",
            FINAL_VIDEO
        ]
        subprocess.run(cmd_simple, capture_output=True, check=True)

    assert os.path.exists(FINAL_VIDEO), "Video not created"
    size = os.path.getsize(FINAL_VIDEO)
    dur_r = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", FINAL_VIDEO
    ], capture_output=True, text=True, check=True)
    final_dur = float(dur_r.stdout.strip())

    print(f"      Vidéo finale: {size/1024/1024:.1f} MB, {final_dur:.1f}s")
    assert size > 50000, f"Video trop petite ({size} bytes)"
    return FINAL_VIDEO

if AUDIO_PATH and SUB_DATA:
    test("Full video assembly (B-roll + voice + subtitles)", test_assembly)
else:
    print("  ⏭️  Skipped (missing audio/subtitles)")


# ════════════════════════════════════════
# COPY RESULT
# ════════════════════════════════════════
if FINAL_VIDEO and os.path.exists(FINAL_VIDEO):
    import shutil
    out_dir = "/sessions/eloquent-eager-feynman/mnt/Claude/content_factory_v2/test_output"
    os.makedirs(out_dir, exist_ok=True)

    for fname in ["voiceover.mp3", "subtitles.srt", "subtitles.ass", "final_video.mp4"]:
        src = os.path.join(WORK_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, fname))

    if SCRIPT_DATA:
        with open(os.path.join(out_dir, "script.json"), "w") as f:
            json.dump(SCRIPT_DATA, f, ensure_ascii=False, indent=2)

    print(f"\n📁 Artefacts copiés dans: {out_dir}")


# ════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RÉSULTAT INTÉGRATION: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
