"""
Vinted Deals Bot v2 — Orchestrateur principal.

Usage:
    python main.py                  # Mode continu
    python main.py --one-shot       # Un seul cycle
    python main.py --dry-run        # Sans envoyer d'alertes
    python main.py --stats          # Afficher les stats 24h
"""

import sys
import time
import random
import signal
import argparse
import logging
from datetime import datetime, timezone

from config import BotConfig
from logger import setup_logger
from db import Database, DealRecord
from vinted_api import VintedAPI
from market_price import MarketPriceEstimator
from scorer import DealScorer
from alerter import Alerter

# Gestion propre du Ctrl+C
_running = True


def _signal_handler(sig, frame):
    global _running
    _running = False
    print("\n[STOP] Arrêt demandé, fin du cycle en cours...")


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


class VintedBot:
    """Orchestrateur du bot de deals Vinted."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.logger = setup_logger(
            "vinted_bot",
            level=config.log_level,
            json_output=config.log_level != "DEBUG"
        )
        self.db = Database(config.db_path)
        self.vinted = VintedAPI(config.vinted, config.proxy)
        self.market = MarketPriceEstimator(
            proxy_config=config.proxy,
            min_samples=config.scoring.min_sold_samples
        )
        self.scorer = DealScorer(config.vinted, config.scoring)
        self.alerter = Alerter(config.alert, dry_run=config.dry_run)
        self._kw_index = 0

    def _select_keywords(self) -> list[str]:
        """Rotation des mots-clés : N par cycle, round-robin."""
        keywords = self.config.vinted.keywords
        n = min(self.config.vinted.keywords_per_cycle, len(keywords))
        selected = []
        for _ in range(n):
            selected.append(keywords[self._kw_index % len(keywords)])
            self._kw_index += 1
        return selected

    def run_cycle(self) -> dict:
        """Exécute un cycle complet : scrape → score → alert."""
        keywords = self._select_keywords()
        cycle_id = self.db.start_cycle(keywords)

        stats = {
            "items_scraped": 0,
            "items_scored": 0,
            "deals_found": 0,
            "alerts_sent": 0,
            "errors": 0,
        }

        self.logger.info(
            f"Cycle {cycle_id} démarré — mots-clés: {keywords}",
            extra={"cycle": cycle_id}
        )

        all_items = []

        # 1. SCRAPE — Récupérer les items de chaque mot-clé
        for kw in keywords:
            if not _running:
                break
            try:
                items = self.vinted.search_items(kw)
                for item in items:
                    item._keyword = kw  # tag le mot-clé source
                all_items.extend(items)
                stats["items_scraped"] += len(items)
            except Exception as e:
                stats["errors"] += 1
                self.logger.error(f"Scrape '{kw}' failed: {e}", extra={"keyword": kw})

        # Déduplication par item_id
        seen_ids = set()
        unique_items = []
        for item in all_items:
            if item.item_id not in seen_ids:
                seen_ids.add(item.item_id)
                unique_items.append(item)

        self.logger.info(f"Items uniques: {len(unique_items)} / {len(all_items)} bruts")

        # 2. SCORE — Évaluer chaque item
        deals = []
        for item in unique_items:
            if not _running:
                break

            # Déjà vu ?
            if self.db.was_seen(item.item_id):
                continue

            stats["items_scored"] += 1

            try:
                # Estimation du prix marché
                market_data = self.market.estimate(item.title)
                if not market_data:
                    # Enregistrer quand même comme "vu" pour ne pas re-tester
                    self.db.mark_seen(DealRecord(
                        item_id=item.item_id, title=item.title,
                        vinted_price=item.price, market_price=0,
                        margin=0, url=item.url,
                        keyword=getattr(item, "_keyword", ""),
                        seen_at=datetime.now(timezone.utc).isoformat(),
                    ))
                    continue

                # Calcul du deal
                deal = self.scorer.compute(item, market_data)

                # Enregistrer dans la DB
                self.db.mark_seen(DealRecord(
                    item_id=item.item_id, title=item.title,
                    vinted_price=item.price,
                    market_price=market_data.median_price,
                    margin=deal.margin if deal else 0,
                    url=item.url,
                    keyword=getattr(item, "_keyword", ""),
                    seen_at=datetime.now(timezone.utc).isoformat(),
                    alerted=bool(deal),
                ))

                if deal:
                    deals.append(deal)

            except Exception as e:
                stats["errors"] += 1
                self.logger.warning(
                    f"Score failed for {item.item_id}: {e}",
                    extra={"item_id": item.item_id, "error_type": "scoring"}
                )

        # Trier par score décroissant
        deals.sort(key=lambda d: d.score, reverse=True)
        stats["deals_found"] = len(deals)

        # 3. ALERT — Envoyer les notifications
        for deal in deals:
            if not _running:
                break
            if not self.db.can_alert(deal.item.item_id, self.config.alert.cooldown_minutes):
                continue
            try:
                sent = self.alerter.send_deal(deal)
                if sent:
                    self.db.mark_alerted(deal.item.item_id)
                    stats["alerts_sent"] += 1
                    self.logger.info(
                        f"Deal alerté: {deal.item.title[:60]} — +{deal.profit:.2f}€ ({deal.margin*100:.0f}%)",
                        extra={
                            "item_id": deal.item.item_id,
                            "price": deal.item.price,
                            "margin": deal.margin,
                        }
                    )
            except Exception as e:
                stats["errors"] += 1
                self.logger.error(f"Alert failed: {e}", extra={"error_type": "alert"})

        # 4. Finalize
        self.db.end_cycle(cycle_id, **stats)
        self.logger.info(
            f"Cycle {cycle_id} terminé — {stats['deals_found']} deals, "
            f"{stats['alerts_sent']} alertes, {stats['errors']} erreurs",
            extra={"cycle": cycle_id, "deals_found": stats["deals_found"]}
        )
        return stats

    def run(self):
        """Boucle principale — exécute des cycles avec pause entre chaque."""
        self.logger.info("Bot Vinted v2 démarré", extra={
            "dry_run": self.config.dry_run,
            "keywords": self.config.vinted.keywords,
            "interval_sec": self.config.check_interval_sec,
            "proxy_enabled": self.config.proxy.enabled,
        })

        if self.config.one_shot:
            self.run_cycle()
            self.logger.info("One-shot terminé")
            return

        cycle_num = 0
        while _running:
            cycle_num += 1
            try:
                self.run_cycle()
            except Exception as e:
                self.logger.error(f"Cycle {cycle_num} crashed: {e}")

            if not _running:
                break

            # Pause avec jitter
            base = self.config.check_interval_sec
            jitter = random.randint(-30, 60)
            sleep_time = max(60, base + jitter)
            self.logger.info(f"Pause {sleep_time}s avant prochain cycle")

            # Sleep interruptible
            for _ in range(sleep_time):
                if not _running:
                    break
                time.sleep(1)

        self.logger.info("Bot arrêté proprement")

    def show_stats(self):
        """Affiche les stats des dernières 24h."""
        stats = self.db.stats_last_24h()
        print("\n📊 Stats dernières 24h:")
        print(f"   Cycles:          {stats['cycles']}")
        print(f"   Items scannés:   {stats['items_scraped']}")
        print(f"   Items uniques:   {stats['unique_items_seen']}")
        print(f"   Deals trouvés:   {stats['deals_found']}")
        print(f"   Alertes envoyées:{stats['alerts_sent']}")
        print(f"   Erreurs:         {stats['errors']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Vinted Deals Bot v2")
    parser.add_argument("--one-shot", action="store_true", help="Un seul cycle puis stop")
    parser.add_argument("--dry-run", action="store_true", help="Pas d'envoi d'alertes réelles")
    parser.add_argument("--stats", action="store_true", help="Afficher les stats 24h")
    parser.add_argument("--debug", action="store_true", help="Mode debug verbose")
    args = parser.parse_args()

    config = BotConfig()

    if args.one_shot:
        config.one_shot = True
    if args.dry_run:
        config.dry_run = True
    if args.debug:
        config.log_level = "DEBUG"

    bot = VintedBot(config)

    if args.stats:
        bot.show_stats()
        return

    bot.run()


if __name__ == "__main__":
    main()
