"""
Génération de scripts vidéo via LLM — Multi-provider (OpenAI, Anthropic, Groq).

Utilise les prompts professionnels pour du short-form optimisé.
Génère script + métadonnées (hooks, CTA, hashtags) en une seule passe.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from config import LLMConfig

logger = logging.getLogger("content_factory")


@dataclass
class VideoScript:
    """Script vidéo complet avec métadonnées."""
    hook: str                   # Les 2-3 premières secondes
    body: str                   # Corps du script (problème + points)
    cta: str                    # Call-to-action final
    full_text: str              # Texte complet pour TTS
    duration_estimate_sec: int  # Estimation de durée (mots/min)
    title: str                  # Titre pour la publication
    description: str            # Description pour les réseaux
    hashtags: list[str] = field(default_factory=list)
    variant: str = "default"    # "emotion", "proof", "urgency"


# ══════════════════════════════════════════════════
# PROMPTS SYSTÈME — Niveau professionnel
# ══════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es un expert en création de contenu short-form (TikTok, Reels, Shorts).
Tu crées des scripts vidéo qui :
- Accrochent en moins de 2 secondes (hook percutant)
- Gardent l'attention avec du rythme et de la valeur
- Terminent par un CTA clair qui pousse à l'action
- Sont écrits pour être DITS à voix haute (langage oral, pas écrit)
- Utilisent un ton direct, FR Belgique/France, sans bullshit corporate

RÈGLES ABSOLUES :
- Hook = max 10 mots, question ou affirmation choc
- Corps = 3 points actionnables MAX, concrets, pas de blabla
- CTA = 1 phrase, action spécifique (follow, lien bio, commentaire)
- Durée totale : 30-45 secondes de parole (environ 80-120 mots)
- JAMAIS de "dans cette vidéo", "bienvenue", "salut les amis"
- Commence DIRECTEMENT par le hook
"""

SCRIPT_PROMPT_TEMPLATE = """Crée un script vidéo short-form (30-45s) sur ce sujet :

SUJET : {topic}
NICHE : {niche}
ANGLE : {angle}
AUDIENCE : {audience}
LANGUE : {language}

Réponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
    "hook": "Le hook (max 10 mots, percutant)",
    "body": "Le corps du script (3 points, langage oral, ~80 mots)",
    "cta": "Le call-to-action final (1 phrase)",
    "title": "Titre pour la publication (max 80 caractères)",
    "description": "Description courte + question engagement",
    "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"]
}}"""

VARIANT_PROMPT_TEMPLATE = """Crée 3 variantes du script suivant, chacune avec un angle différent :

SCRIPT ORIGINAL :
{original_script}

Variantes demandées :
1. ÉMOTION : Joue sur les sentiments, la peur de manquer, l'empathie
2. PREUVE SOCIALE : Utilise des chiffres, témoignages, résultats
3. URGENCE : Crée un sentiment d'urgence, de rareté, de timing

Même CTA pour les 3 : "{cta}"

Réponds en JSON :
{{
    "variants": [
        {{"variant": "emotion", "hook": "...", "body": "...", "cta": "..."}},
        {{"variant": "proof", "hook": "...", "body": "...", "cta": "..."}},
        {{"variant": "urgency", "hook": "...", "body": "...", "cta": "..."}}
    ]
}}"""


class ScriptGenerator:
    """Génère des scripts vidéo via LLM."""

    # Estimation : ~150 mots/minute en FR
    WORDS_PER_MINUTE = 150

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        """Lazy init du client LLM."""
        if self._client:
            return self._client

        provider = self.config.provider.lower()

        if provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=self.config.openai_key)
        elif provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.anthropic_key)
        elif provider == "groq":
            from groq import Groq
            self._client = Groq(api_key=self.config.groq_key)
        else:
            raise ValueError(f"Provider LLM inconnu: {provider}")

        return self._client

    def _call_llm(self, system: str, user: str) -> str:
        """Appel LLM unifié — retourne le texte brut."""
        client = self._get_client()
        provider = self.config.provider.lower()

        if provider in ("openai", "groq"):
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                response_format={"type": "json_object"},
            )
            return response.choices[0].message.content

        elif provider == "anthropic":
            response = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=self.config.temperature,
            )
            return response.content[0].text

        raise ValueError(f"Provider non supporté: {provider}")

    def _estimate_duration(self, text: str) -> int:
        """Estime la durée en secondes d'un texte parlé."""
        word_count = len(text.split())
        return max(10, int(word_count / self.WORDS_PER_MINUTE * 60))

    def generate(self, topic: str, niche: str = "business local",
                 angle: str = "valeur actionnable", audience: str = "PME/indépendants",
                 language: str = "fr") -> VideoScript:
        """Génère un script vidéo complet."""
        logger.info(f"Génération script: {topic[:60]}...")

        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            topic=topic, niche=niche, angle=angle,
            audience=audience, language=language,
        )

        raw = self._call_llm(SYSTEM_PROMPT, prompt)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Tentative d'extraction JSON depuis le texte
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError(f"LLM n'a pas retourné du JSON valide: {raw[:200]}")

        full_text = f"{data['hook']}. {data['body']} {data['cta']}"

        script = VideoScript(
            hook=data["hook"],
            body=data["body"],
            cta=data["cta"],
            full_text=full_text,
            duration_estimate_sec=self._estimate_duration(full_text),
            title=data.get("title", topic[:80]),
            description=data.get("description", ""),
            hashtags=data.get("hashtags", []),
        )

        logger.info(
            f"Script généré: ~{script.duration_estimate_sec}s, "
            f"{len(script.full_text.split())} mots"
        )
        return script

    def generate_variants(self, base_script: VideoScript) -> list[VideoScript]:
        """Génère 3 variantes (émotion, preuve, urgence) d'un script."""
        logger.info("Génération de 3 variantes A/B...")

        prompt = VARIANT_PROMPT_TEMPLATE.format(
            original_script=base_script.full_text,
            cta=base_script.cta,
        )

        raw = self._call_llm(SYSTEM_PROMPT, prompt)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise ValueError("Variants JSON parse failed")

        variants = []
        for v in data.get("variants", []):
            full_text = f"{v['hook']}. {v['body']} {v['cta']}"
            variants.append(VideoScript(
                hook=v["hook"],
                body=v["body"],
                cta=v["cta"],
                full_text=full_text,
                duration_estimate_sec=self._estimate_duration(full_text),
                title=base_script.title,
                description=base_script.description,
                hashtags=base_script.hashtags,
                variant=v.get("variant", "unknown"),
            ))

        logger.info(f"{len(variants)} variantes générées")
        return variants
