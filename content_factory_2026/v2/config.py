"""
Configuration centralisée — Content Factory v2
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


def _int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


@dataclass
class LLMConfig:
    """Configuration du provider LLM pour la génération de scripts."""
    # Provider: "openai", "anthropic", "groq"
    provider: str = os.getenv("LLM_PROVIDER", "openai")
    # Clés API
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    groq_key: str = os.getenv("GROQ_API_KEY", "")
    # Modèle
    model: str = os.getenv("LLM_MODEL", "gpt-4o")
    # Température (créativité)
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.8"))
    max_tokens: int = _int("LLM_MAX_TOKENS", 2000)


@dataclass
class TTSConfig:
    """Configuration Text-to-Speech."""
    # Provider: "openai", "elevenlabs"
    provider: str = os.getenv("TTS_PROVIDER", "openai")
    # OpenAI TTS
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("TTS_OPENAI_MODEL", "tts-1-hd")
    openai_voice: str = os.getenv("TTS_OPENAI_VOICE", "onyx")  # alloy, echo, fable, onyx, nova, shimmer
    # ElevenLabs
    elevenlabs_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model: str = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")


@dataclass
class SubtitleConfig:
    """Configuration sous-titres (Whisper)."""
    # "api" = OpenAI Whisper API, "local" = whisper local
    mode: str = os.getenv("WHISPER_MODE", "api")
    openai_key: str = os.getenv("OPENAI_API_KEY", "")
    model: str = os.getenv("WHISPER_MODEL", "whisper-1")
    # Style des sous-titres
    max_chars_per_line: int = _int("SUBTITLE_MAX_CHARS", 32)
    max_lines: int = _int("SUBTITLE_MAX_LINES", 2)
    font: str = os.getenv("SUBTITLE_FONT", "Montserrat-Bold")
    font_size: int = _int("SUBTITLE_FONT_SIZE", 48)
    font_color: str = os.getenv("SUBTITLE_FONT_COLOR", "white")
    outline_color: str = os.getenv("SUBTITLE_OUTLINE_COLOR", "black")
    outline_width: int = _int("SUBTITLE_OUTLINE_WIDTH", 3)


@dataclass
class MediaConfig:
    """Configuration médias (B-roll, musique)."""
    pexels_key: str = os.getenv("PEXELS_API_KEY", "")
    pixabay_key: str = os.getenv("PIXABAY_API_KEY", "")
    # Répertoire de musiques de fond
    bgm_dir: str = os.getenv("BGM_DIR", "assets/bgm")
    bgm_volume: float = float(os.getenv("BGM_VOLUME", "0.15"))


@dataclass
class PublishConfig:
    """Configuration publication réseaux sociaux."""
    # TikTok
    tiktok_token: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    # Instagram Graph API
    instagram_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    instagram_account_id: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")
    # YouTube
    youtube_key: str = os.getenv("YOUTUBE_API_KEY", "")
    # Scheduling
    auto_publish: bool = _bool("AUTO_PUBLISH", False)


@dataclass
class ContentConfig:
    """Configuration globale du Content Factory."""
    # Langue
    language: str = os.getenv("DEFAULT_LANGUAGE", "fr")
    target_languages: list[str] = field(default_factory=lambda: [
        x.strip() for x in os.getenv("TARGET_LANGUAGES", "fr").split(",") if x.strip()
    ])
    # Durée cible des vidéos (secondes)
    target_duration: int = _int("TARGET_DURATION_SEC", 35)
    # Format de sortie
    output_width: int = _int("OUTPUT_WIDTH", 1080)
    output_height: int = _int("OUTPUT_HEIGHT", 1920)
    fps: int = _int("OUTPUT_FPS", 30)
    # Répertoire de sortie
    output_dir: str = os.getenv("OUTPUT_DIR", "outputs")
    # Sub-configs
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    subtitle: SubtitleConfig = field(default_factory=SubtitleConfig)
    media: MediaConfig = field(default_factory=MediaConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)
