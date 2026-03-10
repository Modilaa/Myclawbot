# Diagnostic Complet — Myclawbot (OpenClaw)
## Bot Vinted + Content Factory 2026

**Date** : 10 mars 2026
**Analysé par** : Claude Opus 4.6
**Repo** : github.com/Modilaa/Myclawbot

---

## VERDICT GLOBAL

Les deux projets sont des **squelettes fonctionnels** mais pas des produits opérationnels. OpenClaw a généré du code qui "a l'air correct" mais qui contient des failles architecturales fondamentales dans les deux cas. Le problème n'est pas un bug isolé — c'est une **conception superficielle** qui ne tient pas compte de la réalité technique de 2026.

---

## PARTIE 1 : BOT VINTED — ANALYSE DÉTAILLÉE

### Ce qui a été fait
Un seul fichier `bot.py` (~400 lignes) qui :
- Scrape le catalogue Vinted via HTML parsing (BeautifulSoup)
- Compare chaque annonce au dernier prix vendu sur eBay
- Calcule un deal (marge nette) et envoie une alerte Telegram
- Supporte Decodo en mode scraper API ou proxy résidentiel
- Gère une base SQLite pour éviter les doublons

### Les 7 problèmes critiques

**1. Approche de scraping fondamentalement cassée**

Le bot fait du scraping HTML du catalogue Vinted (`/catalog?search_text=...`), puis parse chaque annonce individuellement via une seconde requête. En 2026, Vinted utilise **DataDome** comme anti-bot. Le HTML rendu côté serveur ne contient souvent PAS les données produit — elles sont chargées dynamiquement via JavaScript (React SSR hydration).

Le regex `https://www\.vinted\.[a-z]{2,}/items/\d+` sur le HTML brut ne trouvera souvent **rien** car les URLs sont injectées côté client.

**Correction** : Utiliser l'**API interne Vinted** (les endpoints `/api/v2/catalog/items` utilisés par l'app mobile) avec gestion de tokens OAuth. L'app mobile n'est pas protégée par DataDome selon les analyses publiques de la communauté scraping, ce qui rend cette approche bien plus fiable.

**2. Parse des détails via LD+JSON — fragile**

`parse_item_details()` cherche du JSON-LD (`@type: Product`) dans le HTML de chaque annonce. Vinted ne garantit pas ce schéma et le modifie régulièrement. C'est une source de données tertiaire, pas primaire.

**Correction** : L'API interne retourne directement le JSON structuré (titre, prix, photos, vendeur, état, etc.) sans parsing HTML.

**3. Comparaison eBay — méthodologie défaillante**

`extract_ebay_latest_sold_price()` prend le **premier prix** de la page des ventes terminées eBay, parsé depuis le HTML. Problèmes :
- Un seul datapoint (la dernière vente) n'est pas représentatif du prix marché
- Le titre normalisé (`normalize_title`) retire trop d'info — "Pokemon Pikachu 25th" devient "pokemon pikachu 25th", ce qui matche des centaines de cartes différentes sur eBay
- eBay utilise aussi une protection anti-bot, donc le HTML direct peut être bloqué
- Aucune distinction entre état neuf/occasion, édition, langue, etc.

**Correction** : Utiliser l'**API eBay Browse** (gratuite, 5000 appels/jour) avec filtres par catégorie, état, et prix. Calculer un **prix médian** sur les 10-20 dernières ventes, pas la dernière seule.

**4. Pas de gestion de session Vinted**

Le bot utilise un `requests.Session()` basique avec un User-Agent fixe. Pas de gestion de cookies Vinted, pas de token d'authentification, pas de rotation de fingerprint. C'est la recette pour se faire bloquer en quelques requêtes.

**Correction** : Implémenter un cycle complet : obtenir un cookie de session Vinted → extraire le token CSRF → utiliser les headers de l'app mobile (`X-CSRF-Token`, cookies de session) → rotation de proxy entre chaque cycle.

**5. Rate limiting naïf**

`time.sleep(0.7)` entre chaque annonce et `CHECK_INTERVAL_SEC=420` entre les cycles. C'est soit trop agressif (0.7s entre les requêtes détail = détection immédiate) soit trop lent (7 min entre cycles = deals ratés).

**Correction** : Implémenter un **backoff exponentiel adaptatif** avec jitter aléatoire. Varier les intervalles entre 2-8 secondes pour les requêtes détail. Utiliser des cycles courts (60-90s) mais avec peu de requêtes par cycle.

**6. Architecture monolithique**

Tout dans un seul fichier : scraping, parsing, scoring, alerting, DB. Impossible à tester unitairement, impossible à faire évoluer.

**Correction** : Séparer en modules — `scraper.py`, `scorer.py`, `alerter.py`, `models.py`, `config.py`. Utiliser des classes avec injection de dépendances pour pouvoir mocker le scraping dans les tests.

**7. Pas de monitoring ni de métriques**

Aucun logging structuré, pas de métriques (taux de succès scraping, nombre de deals trouvés, latence). Le `MY_ERRORS.md` montre que les problèmes sont découverts manuellement.

**Correction** : Ajouter un logging structuré (JSON), des compteurs Prometheus ou au minimum un dashboard Telegram avec stats quotidiennes.

---

## PARTIE 2 : CONTENT FACTORY — ANALYSE DÉTAILLÉE

### Ce qui a été fait
- Un `demo_pipeline.py` qui génère du texte hardcodé, le découpe en phrases, crée des fichiers SRT, et optionnellement une vidéo noire avec ffmpeg
- Un `produce_batch3.py` qui appelle GPT-4o-mini pour générer 3 scripts
- Des fichiers de documentation (PROMPTS.md, WORKFLOW.md, NICHE_PLAN.md) bien pensés mais non connectés au code
- Un script ffmpeg (`gnr_v3_build.sh`) pour assembler des clips vidéo

### Les 8 problèmes critiques

**1. Le "pipeline" n'est PAS un pipeline — c'est un placeholder**

`demo_pipeline.py` ne fait AUCUN appel à une API. Le script est **hardcodé en dur** :
```
"Hook: Tu veux plus de clients en 2026 ? Voici 3 erreurs fatales..."
```
La "traduction" est un préfixe `[FR]` devant chaque ligne. La "vidéo" est un écran noir avec du texte blanc. Ce n'est pas un MVP, c'est une **maquette en carton**.

**2. `produce_batch3.py` — le seul code fonctionnel est mal écrit**

C'est le seul fichier qui appelle réellement une API (OpenAI). Mais :
- Il utilise `urllib.request` au lieu de `requests` ou `openai` SDK — fragile, sans retry, sans gestion d'erreur
- Il parse manuellement le `.env` au lieu d'utiliser `python-dotenv`
- Il utilise l'endpoint `/v1/responses` (Responses API) avec `output_text` — syntaxe correcte mais aucune gestion des erreurs API, pas de streaming, pas de fallback
- Il écrit des chemins hardcodés (`/data/.openclaw/workspace/...`)
- Les prompts sont minimalistes et ne reprennent RIEN du travail fait dans PROMPTS.md

**3. Aucune génération de voix (TTS)**

Le `.env.example` liste ElevenLabs et Azure TTS, mais **aucun code n'appelle ces APIs**. Sans voix, pas de vidéo short-form viable en 2026.

**Correction** : Intégrer OpenAI TTS (le plus simple — `tts-1` ou `tts-1-hd`), ElevenLabs (meilleure qualité FR), ou Fish Audio (open-source).

**4. Aucune génération d'image/vidéo réelle**

Le bootstrap tente de cloner MoneyPrinterPlus (un projet tiers) mais ne l'intègre pas. Le `gnr_v3_build.sh` assemble des clips qui doivent **déjà exister** — il ne les crée pas.

**Correction** : Intégrer un provider d'images stock (Pexels API est gratuit) + un pipeline de B-roll automatique basé sur les mots-clés du script.

**5. Sous-titres factices**

`to_srt()` assigne un temps fixe de 3 secondes par phrase, quel que soit le contenu. Résultat : décalage total entre audio (qui n'existe pas) et texte.

**Correction** : Utiliser Whisper (OpenAI) pour générer des sous-titres **word-level** synchronisés avec l'audio TTS réel. C'est le standard en 2026.

**6. Pas de publication automatique**

Le `.env.example` liste TikTok, Instagram, Facebook, YouTube… mais **zéro ligne de code** ne publie quoi que ce soit. Le workflow parle de "publier + log performance" mais c'est 100% manuel.

**7. Les excellents prompts de PROMPTS.md sont ignorés**

Le fichier PROMPTS.md contient des prompts bien structurés (hook generator, script 30-45s, variantes A/B, sous-titres optimisés). Mais `produce_batch3.py` utilise un prompt basique inline qui ignore tout ça.

**8. Aucune boucle de feedback / analytics**

Le WORKFLOW.md parle de "Top 3 vidéos (watch time / saves)" et de "patterns gagnants". Mais il n'y a aucun code pour récupérer les analytics des plateformes, aucune base de données de performance, aucune boucle d'amélioration automatisée.

---

## PARTIE 3 : POURQUOI LA QUALITÉ EST SI MAUVAISE

### Le problème fondamental : OpenClaw a fait du "scaffolding", pas de l'ingénierie

1. **Génération de code "impressionnant mais creux"** : Le code généré a l'air professionnel (docstrings, structure, .env.example) mais ne résout pas les vrais problèmes techniques (anti-bot, APIs, pipelines audio/vidéo)

2. **Aucune itération réelle** : Le code a été généré en une passe, sans tests, sans exécution réelle, sans correction. Le `MY_ERRORS.md` montre que les problèmes sont découverts en production

3. **Documentation ≠ Implémentation** : Les fichiers .md (PROMPTS, WORKFLOW, NICHE_PLAN) sont excellents sur papier. Mais le code n'implémente quasi rien de ce qui y est décrit

4. **Pas de connaissance du terrain** : Le bot Vinted ignore DataDome. Le Content Factory ignore les pipelines TTS+Whisper qui sont le standard depuis 2024. C'est du code qui aurait pu être écrit en 2022

---

## PARTIE 4 : PLAN D'ACTION POUR RENDRE LES DEUX OPÉRATIONNELS

### Bot Vinted — Architecture cible

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Scraper    │───→│   Scorer     │───→│   Alerter   │
│  (API Vinted │    │ (eBay API +  │    │ (Telegram + │
│   + Proxy)   │    │  prix médian)│    │  Dashboard) │
└─────────────┘    └──────────────┘    └─────────────┘
       │                  │                    │
       └──────────────────┼────────────────────┘
                          │
                   ┌──────┴──────┐
                   │   SQLite +  │
                   │   Metrics   │
                   └─────────────┘
```

Modules nécessaires :
- `vinted_api.py` : Gestion token + appels API interne + rotation proxy
- `ebay_api.py` : API Browse officielle, prix médian sur N dernières ventes
- `scorer.py` : Calcul de marge avec modèle de coûts configurable
- `alerter.py` : Telegram + formatage + anti-spam
- `db.py` : SQLite avec métriques et historique de prix
- `config.py` : Chargement centralisé depuis .env
- `main.py` : Orchestrateur avec scheduling et monitoring

### Content Factory — Architecture cible

```
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  Script  │──→│   TTS    │──→│  Whisper  │──→│  Video   │──→│ Publish  │
│Generator │   │(ElevenLabs│   │(sous-titres│  │Assembly  │   │(TikTok + │
│ (LLM)   │   │ ou OpenAI)│   │word-level)│   │(ffmpeg)  │   │Instagram)│
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
     │                                              │
     └───────────── B-Roll (Pexels API) ────────────┘
```

Modules nécessaires :
- `script_gen.py` : Appel LLM avec les prompts de PROMPTS.md, variantes A/B
- `tts.py` : ElevenLabs ou OpenAI TTS avec sélection de voix FR
- `subtitles.py` : Whisper word-level → SRT synchronisé
- `broll.py` : Pexels/Pixabay API → téléchargement clips stock
- `assembler.py` : ffmpeg pipeline (montage, sous-titres brûlés, musique)
- `publisher.py` : API TikTok + Instagram Graph + scheduling
- `analytics.py` : Récupération des métriques post-publication
- `main.py` : Orchestrateur du pipeline complet

---

## CONCLUSION

Les deux projets ont une bonne **intention** mais une mauvaise **exécution**. Le contenu stratégique (niches, prompts, workflow) est solide. Le code est un prototype qui ne peut pas fonctionner en production.

Pour les rendre opérationnels au niveau "must de ce qui se fait", il faut essentiellement **tout réécrire** avec une architecture modulaire, des APIs appropriées (pas du scraping HTML), et un vrai pipeline de production.

---

*Diagnostic produit par Claude Opus 4.6 — 10 mars 2026*
