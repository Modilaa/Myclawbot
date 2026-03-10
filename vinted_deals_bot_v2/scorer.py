"""
Scoring des deals — Calcul de rentabilité et filtrage intelligent.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

from config import VintedConfig, ScoringConfig
from vinted_api import VintedItem
from market_price import MarketData

logger = logging.getLogger("vinted_bot")


@dataclass
class Deal:
    """Un deal validé avec tous les chiffres."""
    item: VintedItem
    market: MarketData
    buy_total: float       # Prix Vinted + frais de port achat
    sell_net: float         # Net après frais plateforme + port vente
    profit: float           # sell_net - buy_total
    margin: float           # profit / buy_total (ratio)
    confidence: str         # "high", "medium", "low"
    score: float            # Score composite (0-100)


class DealScorer:
    """Évalue la rentabilité d'un item Vinted vs son prix marché."""

    def __init__(self, vinted_config: VintedConfig, scoring_config: ScoringConfig):
        self.vinted_cfg = vinted_config
        self.scoring_cfg = scoring_config

    # ──────────────────────────────────────────
    # Filtres pré-scoring
    # ──────────────────────────────────────────

    def is_excluded(self, title: str, description: str = "") -> bool:
        """Filtre les items qui ne sont pas des singles (lots, fakes, etc.)."""
        text = f"{title} {description}".lower()

        # Mots exclus
        for word in self.vinted_cfg.exclude_words:
            if word.lower() in text:
                return True

        # Patterns de lots
        if re.search(r"\b\d+\s*(cartes|cards|pcs|pieces|stück)\b", text):
            return True

        # Pack / lot explicite
        if re.search(r"\b(lot|pack|bundle|set|collection)\s*(de|of|x)?\s*\d+", text):
            return True

        return False

    def is_bait_price(self, price: float, title: str) -> bool:
        """Détecte les prix appâts (prix fictifs pour attirer)."""
        title_lower = title.lower()

        # Prix absurdement bas
        if price <= 1.0:
            return True

        # Prix bas + indications de négociation
        if price <= 3.0 and re.search(
            r"(prix\s*(en|dans)\s*description|faire\s*offre|offre|négociable|mp|message)",
            title_lower
        ):
            return True

        return False

    # ──────────────────────────────────────────
    # Calcul de deal
    # ──────────────────────────────────────────

    def compute(self, item: VintedItem, market: MarketData) -> Optional[Deal]:
        """
        Calcule la rentabilité d'un item.
        Retourne un Deal si la marge dépasse le seuil, None sinon.
        """
        # Filtres préliminaires
        if self.is_excluded(item.title):
            return None
        if self.is_bait_price(item.price, item.title):
            return None

        cfg = self.scoring_cfg

        # Coût total d'achat
        buy_total = item.price + cfg.shipping_buy

        # Net de revente (après toutes les commissions)
        market_price = market.median_price
        sell_gross = market_price
        platform_fee = sell_gross * cfg.platform_fee_rate
        payment_fee = sell_gross * cfg.payment_fee_rate + cfg.payment_fee_fixed
        sell_net = sell_gross - platform_fee - payment_fee - cfg.shipping_sell

        # Profit et marge
        profit = sell_net - buy_total
        margin = profit / buy_total if buy_total > 0 else -1

        if margin < cfg.min_net_margin:
            return None

        # Confiance basée sur le nombre de ventes de référence
        if market.sample_count >= 10:
            confidence = "high"
        elif market.sample_count >= 5:
            confidence = "medium"
        else:
            confidence = "low"

        # Score composite (0-100) pour prioriser les meilleurs deals
        score = self._compute_score(margin, market, item)

        return Deal(
            item=item,
            market=market,
            buy_total=round(buy_total, 2),
            sell_net=round(sell_net, 2),
            profit=round(profit, 2),
            margin=round(margin, 4),
            confidence=confidence,
            score=round(score, 1),
        )

    def _compute_score(self, margin: float, market: MarketData, item: VintedItem) -> float:
        """
        Score composite qui prend en compte :
        - La marge (40%)
        - La confiance des données marché (30%)
        - Le profit absolu (20%)
        - La popularité de l'item (10%)
        """
        # Marge normalisée (25% = 0, 100%+ = 40)
        margin_score = min(40, max(0, (margin - 0.25) / 0.75 * 40))

        # Confiance (nombre de ventes)
        confidence_score = min(30, market.sample_count / 15 * 30)

        # Profit absolu (€) — 5€ = 0, 50€+ = 20
        profit = market.median_price - item.price
        profit_score = min(20, max(0, profit / 50 * 20))

        # Popularité Vinted (favourites = demande)
        pop_score = min(10, item.favourite_count / 5 * 10) if item.favourite_count else 0

        return margin_score + confidence_score + profit_score + pop_score
