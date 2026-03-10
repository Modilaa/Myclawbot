"""
Configuration centralisée — Vinted Deals Bot v2
Charge depuis .env avec valeurs par défaut sensibles.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


def _int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float = 0.0) -> float:
    return float(os.getenv(key, str(default)))


def _list(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default).strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


@dataclass
class VintedConfig:
    # --- Vinted ---
    base_url: str = os.getenv("VINTED_BASE_URL", "https://www.vinted.fr")
    country: str = os.getenv("VINTED_COUNTRY", "fr")
    # Recherche
    keywords: list[str] = field(default_factory=lambda: _list(
        "KEYWORDS", "pokemon,topps chrome,panini prizm"
    ))
    keywords_per_cycle: int = _int("KEYWORDS_PER_CYCLE", 2)
    max_items_per_keyword: int = _int("MAX_ITEMS_PER_KEYWORD", 15)
    # Prix
    min_price: float = _float("MIN_PRICE", 5.0)
    max_price: float = _float("MAX_PRICE", 150.0)
    # Exclusions
    exclude_words: list[str] = field(default_factory=lambda: _list(
        "EXCLUDE_WORDS",
        "lot,bundle,x10,x20,x50,proxy,fake,repro,orica,custom,repack,mystery"
    ))


@dataclass
class ProxyConfig:
    # --- Proxy résidentiel (Decodo / Smartproxy / Bright Data) ---
    host: str = os.getenv("PROXY_HOST", "gate.decodo.com")
    port: int = _int("PROXY_PORT", 10001)
    user: str = os.getenv("PROXY_USER", "")
    password: str = os.getenv("PROXY_PASS", "")
    enabled: bool = _bool("PROXY_ENABLED", True)

    @property
    def url(self) -> str:
        if not self.enabled or not self.user:
            return ""
        return f"http://{self.user}:{self.password}@{self.host}:{self.port}"

    @property
    def proxies(self) -> dict:
        u = self.url
        return {"http": u, "https": u} if u else {}


@dataclass
class ScoringConfig:
    # --- Modèle de coûts ---
    min_net_margin: float = _float("MIN_NET_MARGIN", 0.25)
    shipping_buy: float = _float("SHIPPING_BUY", 3.0)
    shipping_sell: float = _float("SHIPPING_SELL", 3.0)
    platform_fee_rate: float = _float("PLATFORM_FEE_RATE", 0.13)  # eBay ~13%
    payment_fee_rate: float = _float("PAYMENT_FEE_RATE", 0.03)
    payment_fee_fixed: float = _float("PAYMENT_FEE_FIXED", 0.35)
    # Nombre minimum de ventes eBay pour valider un prix marché
    min_sold_samples: int = _int("MIN_SOLD_SAMPLES", 3)


@dataclass
class AlertConfig:
    # --- Telegram ---
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    cooldown_minutes: int = _int("ALERT_COOLDOWN_MIN", 120)
    # --- Discord (optionnel) ---
    discord_webhook: str = os.getenv("DISCORD_WEBHOOK_URL", "")


@dataclass
class BotConfig:
    # --- Comportement ---
    check_interval_sec: int = _int("CHECK_INTERVAL_SEC", 300)
    dry_run: bool = _bool("DRY_RUN", True)
    one_shot: bool = _bool("ONE_SHOT", False)
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    db_path: str = os.getenv("DB_PATH", "deals.db")
    # --- Sub-configs ---
    vinted: VintedConfig = field(default_factory=VintedConfig)
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)
