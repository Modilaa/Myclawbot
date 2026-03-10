"""
Alerting — Telegram + Discord avec formatage riche.
"""

import logging
from typing import Optional

import requests

from config import AlertConfig
from scorer import Deal

logger = logging.getLogger("vinted_bot")


class Alerter:
    """Envoie des alertes de deals via Telegram et/ou Discord."""

    def __init__(self, config: AlertConfig, dry_run: bool = True):
        self.config = config
        self.dry_run = dry_run
        self.session = requests.Session()
        self._sent_count = 0

    def send_deal(self, deal: Deal) -> bool:
        """Envoie une alerte pour un deal. Retourne True si envoyé."""
        msg = self._format_deal(deal)

        if self.dry_run:
            logger.info(f"[DRY RUN] Deal alert:\n{msg}")
            self._sent_count += 1
            return True

        success = False

        # Telegram
        if self.config.telegram_token and self.config.telegram_chat_id:
            try:
                self._send_telegram(msg, deal.item.url, deal.item.photo_url)
                success = True
            except Exception as e:
                logger.error(f"Telegram send failed: {e}", extra={"error_type": "telegram"})

        # Discord
        if self.config.discord_webhook:
            try:
                self._send_discord(deal)
                success = True
            except Exception as e:
                logger.error(f"Discord send failed: {e}", extra={"error_type": "discord"})

        if success:
            self._sent_count += 1

        return success

    def send_daily_summary(self, stats: dict) -> bool:
        """Envoie un résumé quotidien des stats du bot."""
        msg = (
            "📊 Résumé 24h — Vinted Bot\n\n"
            f"🔄 Cycles: {stats.get('cycles', 0)}\n"
            f"🔍 Items scannés: {stats.get('items_scraped', 0)}\n"
            f"🆕 Items uniques: {stats.get('unique_items_seen', 0)}\n"
            f"🔥 Deals trouvés: {stats.get('deals_found', 0)}\n"
            f"📩 Alertes envoyées: {stats.get('alerts_sent', 0)}\n"
            f"❌ Erreurs: {stats.get('errors', 0)}\n"
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Daily summary:\n{msg}")
            return True

        if self.config.telegram_token and self.config.telegram_chat_id:
            try:
                self._send_telegram(msg)
                return True
            except Exception as e:
                logger.error(f"Summary send failed: {e}")
        return False

    # ──────────────────────────────────────────
    # Formatage
    # ──────────────────────────────────────────

    def _format_deal(self, deal: Deal) -> str:
        """Formate un deal en message lisible."""
        stars = "🔥" * min(5, int(deal.score / 20) + 1)
        confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(deal.confidence, "⚪")

        return (
            f"{stars} DEAL DÉTECTÉ\n\n"
            f"📦 {deal.item.title}\n"
            f"{'🏷️ ' + deal.item.brand + chr(10) if deal.item.brand else ''}"
            f"\n"
            f"💰 Prix Vinted: {deal.item.price:.2f}€\n"
            f"📈 Prix marché (médiane): {deal.market.median_price:.2f}€\n"
            f"   ↳ sur {deal.market.sample_count} ventes eBay {confidence_emoji}\n"
            f"   ↳ range: {deal.market.min_price:.2f}€ — {deal.market.max_price:.2f}€\n"
            f"\n"
            f"🧮 Coût total: {deal.buy_total:.2f}€\n"
            f"💵 Net revente: {deal.sell_net:.2f}€\n"
            f"✅ Profit: +{deal.profit:.2f}€ ({deal.margin*100:.0f}%)\n"
            f"📊 Score: {deal.score}/100\n"
        )

    # ──────────────────────────────────────────
    # Telegram
    # ──────────────────────────────────────────

    def _send_telegram(self, text: str, url: Optional[str] = None,
                       photo_url: Optional[str] = None):
        token = self.config.telegram_token
        chat_id = self.config.telegram_chat_id
        api_base = f"https://api.telegram.org/bot{token}"

        # Si on a une photo, envoyer en mode photo + caption
        if photo_url:
            try:
                resp = self.session.post(f"{api_base}/sendPhoto", json={
                    "chat_id": chat_id,
                    "photo": photo_url,
                    "caption": text[:1024],  # Telegram caption limit
                    "parse_mode": "HTML",
                    "reply_markup": self._telegram_keyboard(url) if url else None,
                }, timeout=20)
                resp.raise_for_status()
                return
            except Exception:
                pass  # Fallback to text message

        # Message texte
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        if url:
            payload["reply_markup"] = self._telegram_keyboard(url)

        resp = self.session.post(f"{api_base}/sendMessage", json=payload, timeout=20)
        resp.raise_for_status()

    def _telegram_keyboard(self, url: str) -> dict:
        return {
            "inline_keyboard": [
                [{"text": "🛒 Voir l'annonce", "url": url}]
            ]
        }

    # ──────────────────────────────────────────
    # Discord
    # ──────────────────────────────────────────

    def _send_discord(self, deal: Deal):
        embed = {
            "title": f"🔥 Deal: {deal.item.title[:200]}",
            "url": deal.item.url,
            "color": 0x00FF00 if deal.confidence == "high" else 0xFFAA00,
            "fields": [
                {"name": "Prix Vinted", "value": f"{deal.item.price:.2f}€", "inline": True},
                {"name": "Prix marché", "value": f"{deal.market.median_price:.2f}€", "inline": True},
                {"name": "Profit", "value": f"+{deal.profit:.2f}€ ({deal.margin*100:.0f}%)", "inline": True},
                {"name": "Score", "value": f"{deal.score}/100", "inline": True},
                {"name": "Confiance", "value": f"{deal.confidence} ({deal.market.sample_count} ventes)", "inline": True},
            ],
        }
        if deal.item.photo_url:
            embed["thumbnail"] = {"url": deal.item.photo_url}

        resp = self.session.post(
            self.config.discord_webhook,
            json={"embeds": [embed]},
            timeout=20
        )
        resp.raise_for_status()

    @property
    def sent_count(self) -> int:
        return self._sent_count
