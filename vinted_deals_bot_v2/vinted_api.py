"""
Scraper Vinted v2 — Utilise l'API interne JSON (endpoints catalogue).

Stratégie :
1. Obtenir un cookie de session via une requête GET sur la page d'accueil
2. Utiliser ce cookie pour appeler /api/v2/catalog/items (retourne du JSON structuré)
3. Rotation de proxy résidentiel entre les cycles
4. Backoff exponentiel adaptatif en cas de rate limit

Vinted protège son site web avec DataDome, mais les endpoints API internes
retournent du JSON structuré quand on a un cookie de session valide.
"""

import re
import time
import random
import logging
from typing import Optional
from dataclasses import dataclass, field
from urllib.parse import urlencode

import requests

from config import VintedConfig, ProxyConfig

logger = logging.getLogger("vinted_bot")


@dataclass
class VintedItem:
    item_id: str
    title: str
    price: float
    currency: str
    brand: str
    size: str
    url: str
    photo_url: str
    user_login: str
    country: str
    status: str  # ex: "Active"
    favourite_count: int = 0
    view_count: int = 0


class VintedAPI:
    """Client pour l'API interne Vinted (JSON)."""

    # Endpoints connus de l'API interne Vinted
    CATALOG_ENDPOINT = "/api/v2/catalog/items"
    ITEM_ENDPOINT = "/api/v2/items/{item_id}"

    # User-Agents réalistes (rotation)
    USER_AGENTS = [
        "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.82 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]

    def __init__(self, config: VintedConfig, proxy_config: ProxyConfig):
        self.config = config
        self.proxy_config = proxy_config
        self.session = requests.Session()
        self.session.trust_env = False  # ignore system proxies
        self._session_cookie: Optional[str] = None
        self._last_request_time: float = 0
        self._consecutive_errors: int = 0

    def _get_headers(self) -> dict:
        ua = random.choice(self.USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"{self.config.base_url}/",
            "Origin": self.config.base_url,
            "DNT": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        return headers

    def _get_proxies(self) -> dict:
        """Retourne les proxies configurés ou un dict vide."""
        return self.proxy_config.proxies

    def _throttle(self, min_delay: float = 2.0, max_delay: float = 6.0):
        """Délai adaptatif entre les requêtes pour éviter la détection."""
        now = time.time()
        elapsed = now - self._last_request_time
        # Plus on a d'erreurs consécutives, plus on attend
        backoff_factor = min(2 ** self._consecutive_errors, 32)
        target_delay = random.uniform(min_delay, max_delay) * max(1, backoff_factor * 0.5)
        if elapsed < target_delay:
            sleep_time = target_delay - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.time()

    def _ensure_session(self):
        """Obtient un cookie de session Vinted si on n'en a pas."""
        if self._session_cookie:
            return

        logger.info("Obtention d'un cookie de session Vinted...")
        self._throttle(1.0, 2.0)

        try:
            resp = self.session.get(
                self.config.base_url,
                headers=self._get_headers(),
                proxies=self._get_proxies(),
                timeout=30,
                allow_redirects=True
            )
            resp.raise_for_status()

            # Vinted set un cookie '_vinted_fr_session' (ou similaire)
            cookies = self.session.cookies.get_dict()
            session_cookie = None
            for name, value in cookies.items():
                if "vinted" in name.lower() and "session" in name.lower():
                    session_cookie = value
                    break

            if not session_cookie:
                # Parfois le cookie a un nom différent, on prend le plus gros
                if cookies:
                    session_cookie = max(cookies.values(), key=len)

            self._session_cookie = session_cookie
            self._consecutive_errors = 0
            logger.info("Session Vinted obtenue", extra={"cookie_len": len(session_cookie or "")})

        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"Échec obtention session: {e}", extra={"error_type": "session"})
            raise

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Requête HTTP avec retry, backoff et rotation de proxy."""
        max_retries = 4
        last_error = None

        for attempt in range(1, max_retries + 1):
            self._throttle()
            try:
                resp = self.session.request(
                    method, url,
                    headers=self._get_headers(),
                    proxies=self._get_proxies(),
                    timeout=kwargs.pop("timeout", 45),
                    **kwargs
                )

                if resp.status_code == 429:
                    wait = min(120, 10 * (2 ** attempt)) + random.uniform(0, 5)
                    logger.warning(
                        f"Rate limit 429, attente {wait:.0f}s (tentative {attempt}/{max_retries})",
                        extra={"error_type": "rate_limit"}
                    )
                    time.sleep(wait)
                    # Renouveler la session
                    self._session_cookie = None
                    self._ensure_session()
                    continue

                if resp.status_code == 403:
                    logger.warning("Accès 403 — renouvellement de session")
                    self._session_cookie = None
                    self._ensure_session()
                    continue

                resp.raise_for_status()
                self._consecutive_errors = 0
                return resp

            except requests.exceptions.RequestException as e:
                last_error = e
                self._consecutive_errors += 1
                if attempt < max_retries:
                    wait = min(60, 5 * (2 ** attempt)) + random.uniform(0, 3)
                    logger.warning(f"Erreur requête (tentative {attempt}): {e}")
                    time.sleep(wait)

        raise RuntimeError(f"Requête échouée après {max_retries} tentatives: {last_error}")

    def search_items(self, keyword: str) -> list[VintedItem]:
        """
        Recherche des items sur Vinted via l'API catalogue.
        Retourne une liste de VintedItem avec données structurées.
        """
        self._ensure_session()

        params = {
            "page": 1,
            "per_page": self.config.max_items_per_keyword,
            "search_text": keyword,
            "catalog_ids": "",
            "price_from": str(self.config.min_price),
            "price_to": str(self.config.max_price),
            "currency": "EUR",
            "order": "newest_first",
        }

        url = f"{self.config.base_url}{self.CATALOG_ENDPOINT}?{urlencode(params)}"
        logger.info(f"Recherche Vinted: '{keyword}'", extra={"keyword": keyword})

        resp = self._request("GET", url)
        data = resp.json()

        items = []
        raw_items = data.get("items", [])

        for raw in raw_items:
            try:
                item = self._parse_catalog_item(raw)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug(f"Parse item failed: {e}")
                continue

        logger.info(
            f"Vinted '{keyword}': {len(items)} items valides / {len(raw_items)} bruts",
            extra={"keyword": keyword, "items_scraped": len(items)}
        )
        return items

    def _parse_catalog_item(self, raw: dict) -> Optional[VintedItem]:
        """Parse un item depuis la réponse JSON du catalogue."""
        item_id = str(raw.get("id", ""))
        if not item_id:
            return None

        title = raw.get("title", "").strip()
        if not title:
            return None

        # Prix — peut être un dict ou un float selon l'endpoint
        price_data = raw.get("price") or raw.get("total_item_price") or {}
        if isinstance(price_data, dict):
            price = float(price_data.get("amount", 0))
        else:
            try:
                price = float(price_data)
            except (TypeError, ValueError):
                return None

        if price < self.config.min_price or price > self.config.max_price:
            return None

        currency = "EUR"
        if isinstance(price_data, dict):
            currency = price_data.get("currency_code", "EUR")

        # Photo
        photo = raw.get("photo") or {}
        photo_url = photo.get("url", "") if isinstance(photo, dict) else ""

        # Vendeur
        user = raw.get("user") or {}
        user_login = user.get("login", "") if isinstance(user, dict) else ""

        # URL
        url = raw.get("url", f"{self.config.base_url}/items/{item_id}")
        if url.startswith("/"):
            url = f"{self.config.base_url}{url}"

        return VintedItem(
            item_id=item_id,
            title=title,
            price=price,
            currency=currency,
            brand=raw.get("brand_title", "") or "",
            size=raw.get("size_title", "") or "",
            url=url,
            photo_url=photo_url,
            user_login=user_login,
            country=raw.get("user", {}).get("country_title", "") if isinstance(raw.get("user"), dict) else "",
            status=raw.get("status", "Active"),
            favourite_count=raw.get("favourite_count", 0) or 0,
            view_count=raw.get("view_count", 0) or 0,
        )

    def get_item_details(self, item_id: str) -> Optional[dict]:
        """Récupère les détails complets d'un item (description, vendeur, etc.)."""
        self._ensure_session()
        url = f"{self.config.base_url}{self.ITEM_ENDPOINT.format(item_id=item_id)}"

        try:
            resp = self._request("GET", url)
            data = resp.json()
            return data.get("item", data)
        except Exception as e:
            logger.warning(f"Détails item {item_id} indisponibles: {e}")
            return None

    def reset_session(self):
        """Force le renouvellement de la session."""
        self._session_cookie = None
        self.session.cookies.clear()
        logger.info("Session Vinted réinitialisée")
