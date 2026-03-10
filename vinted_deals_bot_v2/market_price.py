"""
Estimation du prix marché — Multi-sources avec prix médian.

Sources supportées :
1. eBay ventes terminées (scraping HTML avec fallback)
2. Cardmarket (si catégorie TCG détectée)

Le prix marché est la MÉDIANE des N dernières ventes, pas un seul datapoint.
"""

import re
import time
import random
import logging
import statistics
from typing import Optional
from urllib.parse import quote_plus, urlencode
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("vinted_bot")


@dataclass
class MarketData:
    """Résultat de l'estimation de prix marché."""
    median_price: float
    min_price: float
    max_price: float
    sample_count: int
    source: str  # "ebay", "cardmarket", etc.
    prices: list[float]
    query_used: str


class MarketPriceEstimator:
    """Estime le prix marché d'un item en croisant plusieurs sources."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Safari/605.1.15",
    ]

    def __init__(self, proxy_config=None, min_samples: int = 3):
        self.session = requests.Session()
        self.session.trust_env = False
        self.proxy_config = proxy_config
        self.min_samples = min_samples
        self._last_request: float = 0

    def _throttle(self):
        elapsed = time.time() - self._last_request
        delay = random.uniform(2.0, 5.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.time()

    def _get(self, url: str, timeout: int = 30) -> str:
        """GET avec headers réalistes et proxy optionnel."""
        self._throttle()
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }
        proxies = self.proxy_config.proxies if self.proxy_config else {}
        resp = self.session.get(url, headers=headers, proxies=proxies, timeout=timeout)
        resp.raise_for_status()
        return resp.text

    # ──────────────────────────────────────────
    # Nettoyage de titre pour la recherche
    # ──────────────────────────────────────────

    @staticmethod
    def clean_query(title: str) -> str:
        """
        Nettoie un titre Vinted pour en faire une requête de recherche eBay.
        Garde les mots importants, retire le bruit.
        """
        t = title.lower()
        # Retirer les infos entre crochets/parenthèses
        t = re.sub(r"[\[\(][^\]\)]*[\]\)]", " ", t)
        # Retirer les caractères spéciaux sauf # (utile pour les n° de cartes)
        t = re.sub(r"[^a-z0-9àâéèêëïôùûüçæœ#/\s-]", " ", t)
        # Retirer les mots inutiles pour la recherche
        noise = {"carte", "card", "cartes", "cards", "tbe", "ttbe", "neuf",
                 "neuve", "mint", "near", "used", "occasion", "envoi",
                 "rapide", "suivi", "lettre", "suivie", "fr", "french",
                 "version", "etat", "état"}
        words = [w for w in t.split() if w not in noise and len(w) > 1]
        # Limiter à 8 mots max pour éviter les recherches trop spécifiques
        return " ".join(words[:8])

    # ──────────────────────────────────────────
    # eBay — Ventes terminées (sold listings)
    # ──────────────────────────────────────────

    def estimate_ebay(self, query: str, max_results: int = 20) -> Optional[MarketData]:
        """
        Récupère les prix des dernières ventes terminées sur eBay.
        Utilise la page de recherche avec filtres LH_Sold + LH_Complete.
        """
        params = {
            "_nkw": query,
            "LH_Sold": "1",
            "LH_Complete": "1",
            "_sop": "13",  # Tri par date (plus récent)
            "rt": "nc",
            "_ipg": str(max_results),
        }
        url = f"https://www.ebay.com/sch/i.html?{urlencode(params)}"

        try:
            html = self._get(url)
        except Exception as e:
            logger.warning(f"eBay fetch failed for '{query}': {e}")
            return None

        prices = self._parse_ebay_prices(html)

        if len(prices) < self.min_samples:
            logger.debug(
                f"eBay '{query}': seulement {len(prices)} ventes (min={self.min_samples})",
                extra={"keyword": query}
            )
            return None

        return MarketData(
            median_price=round(statistics.median(prices), 2),
            min_price=round(min(prices), 2),
            max_price=round(max(prices), 2),
            sample_count=len(prices),
            source="ebay",
            prices=prices,
            query_used=query,
        )

    def _parse_ebay_prices(self, html: str) -> list[float]:
        """Extrait les prix de vente depuis la page eBay sold listings."""
        soup = BeautifulSoup(html, "html.parser")
        prices = []

        # Sélecteurs eBay pour les prix de vente
        # eBay utilise .s-item__price pour le prix principal
        for container in soup.select(".s-item"):
            # Ignorer le premier item (souvent un template)
            title_el = container.select_one(".s-item__title")
            if title_el and "shop on ebay" in title_el.get_text(strip=True).lower():
                continue

            price_el = container.select_one(".s-item__price")
            if not price_el:
                continue

            text = price_el.get_text(" ", strip=True)

            # Gestion des prix en range ("10,00 EUR à 20,00 EUR")
            if " to " in text.lower() or " à " in text.lower() or " a " in text.lower():
                # Prendre la moyenne du range
                nums = re.findall(r"(\d+[\.,]?\d*)", text.replace("\xa0", ""))
                if len(nums) >= 2:
                    try:
                        low = float(nums[0].replace(",", "."))
                        high = float(nums[1].replace(",", "."))
                        avg = (low + high) / 2
                        if 1.0 <= avg <= 5000:
                            prices.append(round(avg, 2))
                    except ValueError:
                        pass
                continue

            # Prix unique
            nums = re.findall(r"(\d+[\.,]?\d*)", text.replace("\xa0", ""))
            if nums:
                try:
                    value = float(nums[0].replace(",", "."))
                    if 1.0 <= value <= 5000:
                        prices.append(round(value, 2))
                except ValueError:
                    pass

        return prices

    # ──────────────────────────────────────────
    # Estimation combinée
    # ──────────────────────────────────────────

    def estimate(self, title: str) -> Optional[MarketData]:
        """
        Estime le prix marché d'un item.
        Essaie d'abord la requête complète, puis une version simplifiée.
        """
        query = self.clean_query(title)
        if not query or len(query) < 3:
            return None

        # Tentative 1 : requête complète
        result = self.estimate_ebay(query)
        if result:
            return result

        # Tentative 2 : requête simplifiée (3 premiers mots significatifs)
        words = query.split()
        if len(words) > 3:
            short_query = " ".join(words[:3])
            result = self.estimate_ebay(short_query)
            if result:
                return result

        return None
