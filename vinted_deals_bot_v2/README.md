# Vinted Deals Bot v2

Bot autonome de détection de bonnes affaires sur Vinted avec alertes Telegram/Discord.

## Architecture

```
main.py          → Orchestrateur (cycles, scheduling, signal handling)
├── config.py    → Configuration centralisée (.env)
├── vinted_api.py→ Client API interne Vinted (JSON, pas HTML)
├── market_price.py → Estimation prix marché (eBay sold, médiane)
├── scorer.py    → Calcul de rentabilité + score composite
├── alerter.py   → Notifications Telegram + Discord
├── db.py        → SQLite (items vus, alertes, stats par cycle)
└── logger.py    → Logging JSON structuré
```

## Différences vs v1

| v1 (OpenClaw) | v2 |
|---|---|
| Scraping HTML (bloqué par DataDome) | API interne Vinted (JSON) |
| 1 seul prix eBay (dernière vente) | Médiane sur N ventes |
| Pas de gestion de session | Cookie session + renouvellement auto |
| sleep fixe 0.7s | Backoff exponentiel adaptatif |
| Monolithique (1 fichier) | 7 modules indépendants |
| print() | Logging JSON structuré |
| Pas de métriques | Stats par cycle + résumé 24h |

## Setup

```bash
cp .env.example .env
# Remplir les valeurs dans .env
pip install -r requirements.txt
python main.py --dry-run --one-shot   # Test
python main.py                        # Production
```

## Commandes

```bash
python main.py                   # Mode continu
python main.py --one-shot        # Un seul cycle
python main.py --dry-run         # Sans alertes réelles
python main.py --stats           # Stats dernières 24h
python main.py --debug           # Mode verbose
```

## Proxy requis

Vinted bloque les IP datacenter. Un proxy résidentiel est nécessaire.
Fournisseurs testés : Decodo (Smartproxy), Bright Data, Oxylabs.
