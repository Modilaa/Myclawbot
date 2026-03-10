"""
Tests unitaires — Content Factory v2
Teste chaque module indépendamment.
Les tests LLM/TTS/Whisper sont mockés (pas d'API key nécessaire).
"""

import os
import sys
import json
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1


# ════════════════════════════════════════
# 1. CONFIG
# ════════════════════════════════════════
print("\n🔧 TEST CONFIG")

def test_config_defaults():
    from config import ContentConfig
    cfg = ContentConfig()
    assert cfg.language == "fr"
    assert cfg.output_width == 1080
    assert cfg.output_height == 1920
    assert cfg.fps == 30
    assert cfg.llm.provider in ("openai", "anthropic", "groq")
    assert cfg.tts.provider in ("openai", "elevenlabs")
    assert cfg.subtitle.max_chars_per_line == 32

test("Config defaults", test_config_defaults)


# ════════════════════════════════════════
# 2. SCRIPT GENERATION (logique sans API)
# ════════════════════════════════════════
print("\n📝 TEST SCRIPT GEN")

def test_script_dataclass():
    from script_gen import VideoScript
    s = VideoScript(
        hook="Tu perds des clients chaque jour",
        body="Voici 3 erreurs. Premièrement...",
        cta="Suis-moi pour plus de conseils",
        full_text="Tu perds des clients chaque jour. Voici 3 erreurs. Premièrement... Suis-moi pour plus de conseils",
        duration_estimate_sec=30,
        title="3 erreurs qui tuent ta visibilité",
        description="La première erreur est la plus courante",
        hashtags=["business", "marketing", "PME"],
    )
    assert s.hook == "Tu perds des clients chaque jour"
    assert len(s.hashtags) == 3
    assert s.variant == "default"

test("VideoScript dataclass", test_script_dataclass)

def test_duration_estimate():
    from script_gen import ScriptGenerator
    from config import LLMConfig
    gen = ScriptGenerator(LLMConfig())
    # ~150 mots/min en FR
    dur = gen._estimate_duration("un deux trois quatre cinq six sept huit neuf dix " * 15)
    assert 50 < dur < 80, f"Expected ~60s for 150 words, got {dur}"

test("Duration estimation (~150 mots/min)", test_duration_estimate)

def test_prompt_templates():
    from script_gen import SCRIPT_PROMPT_TEMPLATE, SYSTEM_PROMPT
    # Vérifier que les templates sont formatables
    filled = SCRIPT_PROMPT_TEMPLATE.format(
        topic="test", niche="immo", angle="valeur",
        audience="PME", language="fr"
    )
    assert "test" in filled
    assert "immo" in filled
    assert len(SYSTEM_PROMPT) > 100  # Prompt système substantiel

test("Prompt templates are formattable", test_prompt_templates)


# ════════════════════════════════════════
# 3. TTS (logique sans API)
# ════════════════════════════════════════
print("\n🎙️ TEST TTS")

def test_tts_split_text():
    from tts import TTSEngine
    # Texte court : pas de split
    chunks = TTSEngine._split_text("Hello world.", 4000)
    assert len(chunks) == 1

    # Texte long : split sur les phrases
    long_text = "Première phrase. " * 300  # ~5100 chars
    chunks = TTSEngine._split_text(long_text, 4000)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk) <= 4000, f"Chunk too long: {len(chunk)}"

test("TTS text splitting", test_tts_split_text)


# ════════════════════════════════════════
# 4. SUBTITLES
# ════════════════════════════════════════
print("\n💬 TEST SUBTITLES")

def test_subtitle_grouping():
    from subtitles import SubtitleGenerator, Word
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig())

    words = [
        Word("Tu", 0.0, 0.2),
        Word("perds", 0.2, 0.5),
        Word("des", 0.5, 0.6),
        Word("clients", 0.6, 1.0),
        Word("chaque", 1.0, 1.3),
        Word("jour.", 1.3, 1.6),
        Word("Voici", 2.0, 2.3),
        Word("trois", 2.3, 2.6),
        Word("erreurs", 2.6, 3.0),
        Word("fatales.", 3.0, 3.5),
    ]

    segments = gen._group_into_segments(words)
    assert len(segments) >= 1, "Should produce at least 1 segment"
    # Vérifier que les timestamps sont cohérents
    for seg in segments:
        assert seg.start < seg.end, f"Start should be < end: {seg.start} >= {seg.end}"
        assert seg.start >= 0
        assert len(seg.text) > 0

test("Subtitle word grouping", test_subtitle_grouping)

def test_subtitle_srt_format():
    from subtitles import SubtitleGenerator
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig())
    assert gen._srt_time(0) == "00:00:00,000"
    assert gen._srt_time(65.5) == "00:01:05,500"
    assert gen._srt_time(3723.123) == "01:02:03,123"

test("SRT time formatting", test_subtitle_srt_format)

def test_subtitle_ass_format():
    from subtitles import SubtitleGenerator
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig())
    assert gen._ass_time(0) == "0:00:00.00"
    assert gen._ass_time(65.5) == "0:01:05.50"

test("ASS time formatting", test_subtitle_ass_format)

def test_subtitle_text_formatting():
    from subtitles import SubtitleGenerator
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig(max_chars_per_line=32, max_lines=2))

    short = gen._format_text("Hello world")
    assert "\n" not in short  # Fits on one line

    long_text = "Ceci est un texte beaucoup plus long qui dépasse la limite"
    formatted = gen._format_text(long_text)
    lines = formatted.split("\n")
    assert len(lines) <= 2, f"Max 2 lines, got {len(lines)}"
    for line in lines:
        assert len(line) <= 33, f"Line too long: {len(line)} chars: '{line}'"  # +1 for truncation char

test("Subtitle text formatting (mobile)", test_subtitle_text_formatting)

def test_subtitle_srt_export():
    from subtitles import SubtitleGenerator, SubtitleSegment
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig())

    segments = [
        SubtitleSegment(1, 0.0, 1.5, "Tu perds des clients"),
        SubtitleSegment(2, 2.0, 3.5, "Voici trois erreurs"),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False) as f:
        path = f.name

    try:
        gen._export_srt(segments, path)
        with open(path, "r") as f:
            content = f.read()
        assert "1\n" in content
        assert "00:00:00,000 --> 00:00:01,500" in content
        assert "Tu perds des clients" in content
        assert "2\n" in content
    finally:
        os.unlink(path)

test("SRT file export", test_subtitle_srt_export)

def test_subtitle_ass_export():
    from subtitles import SubtitleGenerator, SubtitleSegment
    from config import SubtitleConfig
    gen = SubtitleGenerator(SubtitleConfig())

    segments = [
        SubtitleSegment(1, 0.0, 1.5, "Tu perds des clients"),
        SubtitleSegment(2, 2.0, 3.5, "Voici trois\nerreurs"),
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ass", delete=False) as f:
        path = f.name

    try:
        gen._export_ass(segments, path)
        with open(path, "r") as f:
            content = f.read()
        assert "[Script Info]" in content
        assert "Dialogue:" in content
        assert "Tu perds des clients" in content
        assert "\\N" in content  # Newline ASS
    finally:
        os.unlink(path)

test("ASS file export", test_subtitle_ass_export)


# ════════════════════════════════════════
# 5. B-ROLL
# ════════════════════════════════════════
print("\n🎬 TEST B-ROLL")

def test_visual_keyword_extraction():
    from broll import BRollProvider
    kws = BRollProvider.extract_visual_keywords(
        "3 erreurs qui font perdre des clients à ton restaurant",
        niche="restaurant"
    )
    assert len(kws) >= 2
    assert any("restaurant" in k or "food" in k or "cooking" in k for k in kws)

test("Visual keyword extraction", test_visual_keyword_extraction)

def test_visual_keywords_generic():
    from broll import BRollProvider
    kws = BRollProvider.extract_visual_keywords("Test text", niche="unknown")
    assert len(kws) >= 2  # Should fallback to generics

test("Visual keywords generic fallback", test_visual_keywords_generic)


# ════════════════════════════════════════
# 6. ASSEMBLER (ffmpeg)
# ════════════════════════════════════════
print("\n🎞️ TEST ASSEMBLER")

def test_ffmpeg_available():
    result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    assert result.returncode == 0

test("ffmpeg is available", test_ffmpeg_available)

def test_gradient_background():
    from assembler import VideoAssembler
    from config import ContentConfig
    asm = VideoAssembler(ContentConfig())

    with tempfile.TemporaryDirectory() as td:
        output = os.path.join(td, "bg.mp4")
        asm._generate_gradient_background(output, 5.0)
        assert os.path.exists(output), "Background video should be created"
        # Vérifier la durée
        dur = asm._get_duration(output)
        assert 4.0 < dur < 6.0, f"Expected ~5s, got {dur}"

test("Generate gradient background (ffmpeg)", test_gradient_background)

def test_full_assembly_no_broll():
    """Test complet d'assemblage avec un audio synthétique (pas d'API)."""
    from assembler import VideoAssembler
    from subtitles import SubtitleGenerator, SubtitleSegment
    from config import ContentConfig, SubtitleConfig

    config = ContentConfig()
    asm = VideoAssembler(config)
    sub_gen = SubtitleGenerator(SubtitleConfig())

    with tempfile.TemporaryDirectory() as td:
        # Créer un audio de test (5s de silence)
        audio_path = os.path.join(td, "test_voice.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=44100:duration=5",
            "-c:a", "libmp3lame", audio_path
        ], capture_output=True, check=True)

        # Créer des sous-titres de test
        segments = [
            SubtitleSegment(1, 0.0, 2.0, "Premiere ligne"),
            SubtitleSegment(2, 2.5, 4.5, "Deuxieme ligne"),
        ]
        ass_path = os.path.join(td, "test.ass")
        sub_gen._export_ass(segments, ass_path)

        # Assembler sans B-roll (fallback gradient)
        output = os.path.join(td, "final.mp4")
        asm.assemble(
            audio_path=audio_path,
            subtitle_ass_path=ass_path,
            broll_clips=[],
            output_path=output,
        )

        assert os.path.exists(output), "Final video should be created"
        size = os.path.getsize(output)
        assert size > 10000, f"Video too small ({size} bytes), likely broken"
        dur = asm._get_duration(output)
        assert 4.0 < dur < 6.0, f"Expected ~5s, got {dur}"

test("Full assembly pipeline (no B-roll, synthetic audio)", test_full_assembly_no_broll)


# ════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RÉSULTAT: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
