import os
import re
import time
import json
import random
import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "deals.db")

VINTED_BASE = os.getenv("VINTED_BASE", "https://www.vinted.fr")
COUNTRY_CODE = os.getenv("COUNTRY_CODE", "FR")
CHECK_INTERVAL_SEC = int(os.getenv("CHECK_INTERVAL_SEC", "420"))
MIN_NET_MARGIN = float(os.getenv("MIN_NET_MARGIN", "0.25"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "10"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "100"))
SHIPPING_BUY = float(os.getenv("SHIPPING_BUY", "3.0"))
SHIPPING_SELL = float(os.getenv("SHIPPING_SELL", "3.0"))
EBAY_FEE_RATE = float(os.getenv("EBAY_FEE_RATE", "0.13"))
PAYMENT_FEE_RATE = float(os.getenv("PAYMENT_FEE_RATE", "0.03"))
PAYMENT_FEE_FIXED = float(os.getenv("PAYMENT_FEE_FIXED", "0.35"))
ALERT_COOLDOWN_MIN = int(os.getenv("ALERT_COOLDOWN_MIN", "180"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
ONE_SHOT = os.getenv("ONE_SHOT", "true").lower() == "true"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DECODO_USER = os.getenv("DECODO_USERNAME", "")
DECODO_PASS = os.getenv("DECODO_PASSWORD", "")
DECODO_BASIC_AUTH = os.getenv("DECODO_BASIC_AUTH", "")
DECODO_SCRAPER_URL = os.getenv("DECODO_SCRAPER_URL", "https://scraper-api.decodo.com/v2/scrape")
DECODO_MODE = os.getenv("DECODO_MODE", "scraper").lower()  # scraper|proxy
DECODO_PROXY_HOST = os.getenv("DECODO_PROXY_HOST", "")
DECODO_PROXY_PORT = os.getenv("DECODO_PROXY_PORT", "10001")
DECODO_PROXY_USER = os.getenv("DECODO_PROXY_USER", "")
DECODO_PROXY_PASS = os.getenv("DECODO_PROXY_PASS", "")
MAX_ITEMS_PER_KEYWORD = int(os.getenv("MAX_ITEMS_PER_KEYWORD", "20"))
KEYWORDS_PER_CYCLE = int(os.getenv("KEYWORDS_PER_CYCLE", "1"))

KEYWORDS = [
    "pokemon",
    "topps",
    "panini",
]
KW_INDEX = 0

EXCLUDE_WORDS = [
    "lot",
    "bundle",
    "x10",
    "x20",
    "proxy",
    "fake",
    "repro",
    "orica",
]

session = requests.Session()
session.trust_env = False  # ignore system proxy vars that can cause 407
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }
)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_items (
            item_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            seen_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_alerts (
            item_id TEXT PRIMARY KEY,
            sent_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"\[[^\]]+\]", " ", t)
    t = re.sub(r"[^a-z0-9\s#-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_single_card(title: str, description: str = "") -> bool:
    text = f"{title} {description}".lower()
    if any(w in text for w in EXCLUDE_WORDS):
        return False
    if re.search(r"\b\d+\s*(cartes|cards|pcs|pieces)\b", text):
        return False
    return True


def is_bait_price(price: float, title: str) -> bool:
    if price <= 2.0:
        return True
    if price <= 5.0 and re.search(r"\bprix\s*en\s*description\b|faire\s*offre", title.lower()):
        return True
    return False


def decodo_headers():
    auth = DECODO_BASIC_AUTH.strip()
    if not auth and DECODO_USER and DECODO_PASS:
        import base64

        auth = base64.b64encode(f"{DECODO_USER}:{DECODO_PASS}".encode()).decode()
    if not auth:
        raise RuntimeError("Decodo credentials manquants (DECODO_BASIC_AUTH ou DECODO_USERNAME/DECODO_PASSWORD)")
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }


def decodo_scrape_api(url: str) -> str:
    payload = {"url": url}
    last_err = None

    for attempt in range(1, 6):
        try:
            r = session.post(DECODO_SCRAPER_URL, headers=decodo_headers(), json=payload, timeout=70)
            if r.status_code == 429:
                wait_s = min(120, 8 * attempt)
                print(f"[WARN] Decodo 429, retry dans {wait_s}s (attempt {attempt}/5)")
                time.sleep(wait_s)
                continue

            r.raise_for_status()
            data = r.json()
            results = data.get("results") or []
            if not results:
                raise RuntimeError("Decodo scrape vide")
            content = results[0].get("content")
            if not content:
                raise RuntimeError("Decodo: champ content absent")
            return content
        except Exception as e:
            last_err = e
            if attempt < 5:
                wait_s = min(60, 4 * attempt)
                print(f"[WARN] Decodo scrape retry {attempt}/5: {e}")
                time.sleep(wait_s)
            else:
                break

    raise RuntimeError(f"Decodo scrape API failed after retries: {last_err}")


def decodo_scrape_proxy(url: str) -> str:
    if not (DECODO_PROXY_HOST and DECODO_PROXY_USER and DECODO_PROXY_PASS):
        raise RuntimeError("Proxy Decodo incomplet (host/user/pass manquants)")

    proxy_url = f"http://{DECODO_PROXY_USER}:{DECODO_PROXY_PASS}@{DECODO_PROXY_HOST}:{DECODO_PROXY_PORT}"
    proxies = {"http": proxy_url, "https": proxy_url}
    r = session.get(url, proxies=proxies, timeout=70)
    r.raise_for_status()
    return r.text


def decodo_scrape(url: str) -> str:
    if DECODO_MODE == "proxy":
        return decodo_scrape_proxy(url)
    if DECODO_MODE == "direct":
        return fetch_url(url)

    # mode scraper (default): fallback en direct si Decodo est throttlé
    try:
        return decodo_scrape_api(url)
    except Exception as e:
        print(f"[WARN] Decodo indisponible, fallback direct: {e}")
        return fetch_url(url)


def parse_item_details(item_url: str):
    html = decodo_scrape(item_url)
    soup = BeautifulSoup(html, "html.parser")

    title = None
    price = None
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, list):
            candidates = data
        else:
            candidates = [data]

        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") == "Product":
                title = obj.get("name") or title
                offers = obj.get("offers") or {}
                p = offers.get("price")
                try:
                    price = float(str(p).replace(",", "."))
                except Exception:
                    pass
                break
        if title and price is not None:
            break

    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else ""

    item_id_match = re.search(r"/items/(\d+)", item_url)
    item_id = item_id_match.group(1) if item_id_match else ""

    return {
        "id": item_id,
        "title": title or "",
        "price": price,
        "url": item_url,
    }


def fetch_vinted_items(keyword: str):
    catalog_url = (
        f"{VINTED_BASE}/catalog?search_text={quote_plus(keyword)}"
        f"&price_from={int(MIN_PRICE)}&price_to={int(MAX_PRICE)}&order=newest_first"
    )
    html = decodo_scrape(catalog_url)

    urls = set()
    for m in re.finditer(r'https://www\\.vinted\\.[a-z]{2,}/items/\\d+[^"\\s<]*', html):
        u = m.group(0).split("?", 1)[0]
        urls.add(u)

    if not urls:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/items/" in href:
                full = urljoin(VINTED_BASE, href).split("?", 1)[0]
                if re.search(r"/items/\d+", full):
                    urls.add(full)

    picked = list(urls)[:MAX_ITEMS_PER_KEYWORD]
    items = []
    for u in picked:
        try:
            details = parse_item_details(u)
            if details.get("id") and details.get("title") and details.get("price") is not None:
                items.append(details)
            time.sleep(0.7)
        except Exception as e:
            print(f"[WARN] parse item fail {u}: {e}")

    return items


def extract_ebay_latest_sold_price(query: str):
    # _sop=13 => tri par ventes terminées les plus récentes
    url = (
        f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(query)}"
        f"&LH_Sold=1&LH_Complete=1&_sop=13&rt=nc"
    )
    html = fetch_url(url)
    soup = BeautifulSoup(html, "html.parser")

    prices = []
    for el in soup.select(".s-item__price"):
        text = el.get_text(" ", strip=True)
        m = re.findall(r"(\d+[\.,]?\d*)", text.replace("\xa0", " "))
        if not m:
            continue
        try:
            value = float(m[0].replace(",", "."))
            if 1 <= value <= 10000:
                prices.append(value)
        except ValueError:
            continue

    if not prices:
        return None

    # Le premier prix correspond à la dernière vente réussie (tri récent)
    return prices[0]


def fetch_url(url: str) -> str:
    r = session.get(url, timeout=45)
    r.raise_for_status()
    return r.text


def compute_deal(vinted_price: float, market_price: float):
    buy_total = vinted_price + SHIPPING_BUY
    sell_net = market_price * (1 - EBAY_FEE_RATE - PAYMENT_FEE_RATE) - PAYMENT_FEE_FIXED - SHIPPING_SELL
    profit = sell_net - buy_total
    margin = profit / buy_total if buy_total > 0 else -1
    return {
        "buy_total": round(buy_total, 2),
        "sell_net": round(sell_net, 2),
        "profit": round(profit, 2),
        "margin": round(margin, 4),
    }


def was_seen(item_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM seen_items WHERE item_id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row)


def mark_seen(item_id: str, title: str, url: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO seen_items(item_id, title, url, seen_at) VALUES(?,?,?,?)",
        (item_id, title, url, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def can_alert(item_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT sent_at FROM sent_alerts WHERE item_id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return True

    sent_at = datetime.fromisoformat(row[0])
    elapsed_min = (datetime.now(timezone.utc) - sent_at).total_seconds() / 60
    return elapsed_min >= ALERT_COOLDOWN_MIN


def mark_alert(item_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO sent_alerts(item_id, sent_at) VALUES(?,?)",
        (item_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def send_telegram(text: str, url: str | None = None):
    if DRY_RUN:
        print("\n=== DEAL ALERT (DRY RUN) ===")
        print(text)
        print("===========================\n")
        return

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram token/chat_id manquant, alerte non envoyée.")
        return

    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    }

    if url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": "🛒 Ouvrir l'annonce", "url": url}]]
        }

    r = session.post(api, json=payload, timeout=20)
    r.raise_for_status()


def score_and_alert(items):
    for item in items:
        item_id = str(item.get("id") or "")
        if not item_id:
            continue

        title = item.get("title", "")
        if not title or not is_single_card(title):
            continue

        raw_price = item.get("price")
        try:
            if isinstance(raw_price, dict):
                price = float(raw_price.get("amount"))
            else:
                price = float(raw_price)
        except (TypeError, ValueError):
            continue

        if price < MIN_PRICE or price > MAX_PRICE:
            continue
        if is_bait_price(price, title):
            continue

        url = item.get("url") or f"{VINTED_BASE}/items/{item_id}"

        if was_seen(item_id):
            continue
        mark_seen(item_id, title, url)

        query = normalize_title(title)
        latest_sale_price = extract_ebay_latest_sold_price(query)
        if latest_sale_price is None:
            continue

        market_price = latest_sale_price
        deal = compute_deal(price, market_price)

        if deal["margin"] < MIN_NET_MARGIN:
            continue
        if not can_alert(item_id):
            continue

        msg = (
            f"🔥 DEAL CARTE DETECTÉ\n"
            f"Titre: {title}\n"
            f"Prix Vinted: {price:.2f}€\n"
            f"Dernière vente eBay: {market_price:.2f}€\n"
            f"Coût total achat: {deal['buy_total']:.2f}€\n"
            f"Net revente estimé: {deal['sell_net']:.2f}€\n"
            f"Profit net estimé: {deal['profit']:.2f}€\n"
            f"Marge nette: {deal['margin']*100:.1f}%\n"
            f"URL: {url}"
        )

        send_telegram(msg, url=url)
        mark_alert(item_id)


def run_once():
    global KW_INDEX
    all_items = []

    # Rotation contrôlée: n mots-clés par cycle (évite la saturation)
    kpc = max(1, min(KEYWORDS_PER_CYCLE, len(KEYWORDS)))
    active_keywords = []
    for _ in range(kpc):
        active_keywords.append(KEYWORDS[KW_INDEX % len(KEYWORDS)])
        KW_INDEX += 1

    for kw in active_keywords:
        try:
            items = fetch_vinted_items(kw)
            print(f"[OK] Vinted '{kw}': {len(items)} annonces")
            all_items.extend(items)
            time.sleep(1.2)
        except Exception as e:
            print(f"[ERR] Vinted '{kw}': {e}")

    # dedupe simple by item id
    dedup = {}
    for it in all_items:
        iid = str(it.get("id") or "")
        if iid:
            dedup[iid] = it

    print(f"[INFO] Annonces uniques analysées: {len(dedup)}")
    score_and_alert(list(dedup.values()))


def main():
    init_db()
    print("[BOOT] Vinted Card Deals Bot démarré")
    print(json.dumps(
        {
            "dry_run": DRY_RUN,
            "min_margin": MIN_NET_MARGIN,
            "price_range": [MIN_PRICE, MAX_PRICE],
            "interval_sec": CHECK_INTERVAL_SEC,
            "country": COUNTRY_CODE,
            "decodo_mode": DECODO_MODE,
        },
        indent=2,
        ensure_ascii=False,
    ))

    if ONE_SHOT:
        run_once()
        print("[DONE] One-shot terminé")
        return

    while True:
        run_once()
        sleep_for = CHECK_INTERVAL_SEC + random.randint(-20, 40)
        sleep_for = max(120, sleep_for)
        print(f"[SLEEP] {sleep_for}s")
        time.sleep(sleep_for)


if __name__ == "__main__":
    main()
