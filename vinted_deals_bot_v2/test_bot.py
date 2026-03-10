"""
Tests unitaires — Vinted Deals Bot v2
Teste chaque module indépendamment avec des données mockées.
"""

import os
import sys
import json
import tempfile

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        FAIL += 1


# ════════════════════════════════════════
# 1. CONFIG
# ════════════════════════════════════════
print("\n🔧 TEST CONFIG")

def test_config_defaults():
    from config import BotConfig
    cfg = BotConfig()
    assert cfg.vinted.base_url == "https://www.vinted.fr"
    assert cfg.vinted.min_price == 5.0
    assert cfg.scoring.min_net_margin == 0.25
    assert cfg.dry_run == True
    assert isinstance(cfg.vinted.keywords, list)

test("Config defaults load correctly", test_config_defaults)

def test_config_proxy():
    from config import ProxyConfig
    p = ProxyConfig(host="gate.test.com", port=10001, user="usr", password="pwd", enabled=True)
    assert "usr:pwd@gate.test.com:10001" in p.url
    p2 = ProxyConfig(enabled=False)
    assert p2.url == ""
    assert p2.proxies == {}

test("Proxy config URL generation", test_config_proxy)


# ════════════════════════════════════════
# 2. DATABASE
# ════════════════════════════════════════
print("\n💾 TEST DATABASE")

def test_db_init():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        from db import Database, DealRecord
        db = Database(path)
        # Tables should exist
        import sqlite3
        conn = sqlite3.connect(path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "seen_items" in tables
        assert "alerts" in tables
        assert "cycle_stats" in tables
    finally:
        os.unlink(path)

test("Database schema creation", test_db_init)

def test_db_seen_items():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        from db import Database, DealRecord
        db = Database(path)
        assert db.was_seen("item123") == False
        db.mark_seen(DealRecord(
            item_id="item123", title="Test Card", vinted_price=10.0,
            market_price=25.0, margin=0.5, url="https://vinted.fr/items/123",
            keyword="pokemon", seen_at="2026-03-10T12:00:00Z"
        ))
        assert db.was_seen("item123") == True
        assert db.was_seen("item999") == False
    finally:
        os.unlink(path)

test("DB seen items tracking", test_db_seen_items)

def test_db_alerts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        from db import Database
        db = Database(path)
        assert db.can_alert("item1", cooldown_min=10) == True
        db.mark_alerted("item1")
        assert db.can_alert("item1", cooldown_min=10) == False
    finally:
        os.unlink(path)

test("DB alert cooldown", test_db_alerts)

def test_db_cycle_stats():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        from db import Database
        db = Database(path)
        cid = db.start_cycle(["pokemon", "topps"])
        assert cid >= 1
        db.end_cycle(cid, items_scraped=20, deals_found=3, alerts_sent=2, errors=0)
        stats = db.stats_last_24h()
        assert stats["cycles"] == 1
        assert stats["items_scraped"] == 20
        assert stats["deals_found"] == 3
    finally:
        os.unlink(path)

test("DB cycle stats", test_db_cycle_stats)


# ════════════════════════════════════════
# 3. SCORING
# ════════════════════════════════════════
print("\n📊 TEST SCORING")

def test_scorer_exclusions():
    from config import VintedConfig, ScoringConfig
    from scorer import DealScorer
    scorer = DealScorer(VintedConfig(), ScoringConfig())
    assert scorer.is_excluded("Lot de 10 cartes Pokemon") == True
    assert scorer.is_excluded("Carte Pokemon Pikachu 25th") == False
    assert scorer.is_excluded("Bundle Topps Chrome") == True
    assert scorer.is_excluded("Fake Orica Charizard") == True
    assert scorer.is_excluded("Panini Prizm Silver #123") == False

test("Scorer exclusion filters", test_scorer_exclusions)

def test_scorer_bait_detection():
    from config import VintedConfig, ScoringConfig
    from scorer import DealScorer
    scorer = DealScorer(VintedConfig(), ScoringConfig())
    assert scorer.is_bait_price(0.50, "Pikachu rare") == True
    assert scorer.is_bait_price(1.00, "Carte faire offre") == True
    assert scorer.is_bait_price(2.00, "prix en description") == True
    assert scorer.is_bait_price(15.0, "Pikachu 25th") == False

test("Scorer bait price detection", test_scorer_bait_detection)

def test_scorer_deal_computation():
    from config import VintedConfig, ScoringConfig
    from scorer import DealScorer
    from vinted_api import VintedItem
    from market_price import MarketData

    scorer = DealScorer(VintedConfig(), ScoringConfig(min_net_margin=0.20))

    item = VintedItem(
        item_id="1", title="Pikachu 25th Anniversary",
        price=12.0, currency="EUR", brand="Pokemon",
        size="", url="https://vinted.fr/items/1",
        photo_url="", user_login="seller1",
        country="FR", status="Active",
    )

    market = MarketData(
        median_price=35.0, min_price=28.0, max_price=45.0,
        sample_count=8, source="ebay", prices=[28,30,32,35,36,38,40,45],
        query_used="pikachu 25th anniversary"
    )

    deal = scorer.compute(item, market)
    assert deal is not None, "Deal should be detected"
    assert deal.profit > 0, f"Profit should be positive, got {deal.profit}"
    assert deal.margin > 0.20, f"Margin should be > 20%, got {deal.margin}"
    assert deal.confidence == "medium", f"Should be medium confidence (8 samples)"
    assert 0 <= deal.score <= 100

    # Test avec mauvais deal (prix trop élevé)
    item_bad = VintedItem(
        item_id="2", title="Carte commune",
        price=50.0, currency="EUR", brand="",
        size="", url="https://vinted.fr/items/2",
        photo_url="", user_login="seller2",
        country="FR", status="Active",
    )
    market_bad = MarketData(
        median_price=20.0, min_price=15.0, max_price=25.0,
        sample_count=5, source="ebay", prices=[15,18,20,22,25],
        query_used="carte commune"
    )
    deal_bad = scorer.compute(item_bad, market_bad)
    assert deal_bad is None, "Bad deal should not pass"

test("Scorer deal computation (good + bad deal)", test_scorer_deal_computation)


# ════════════════════════════════════════
# 4. MARKET PRICE
# ════════════════════════════════════════
print("\n💰 TEST MARKET PRICE")

def test_clean_query():
    from market_price import MarketPriceEstimator
    q = MarketPriceEstimator.clean_query
    # Doit garder les mots importants, retirer le bruit
    r1 = q("Carte Pokemon Pikachu 25th [FR] TBE")
    assert "pokemon" in r1, f"Expected 'pokemon' in '{r1}'"
    assert "pikachu" in r1
    assert "25th" in r1
    assert "tbe" not in r1  # noise word
    assert "fr" not in r1.split()  # noise word (mais attention à sous-chaîne)
    # Retirer les mots de remplissage comme envoi/suivi
    result = q("[NEUF] Pokemon Charizard VMAX #100/200 envoi rapide suivi")
    assert "pokemon" in result
    assert "charizard" in result
    assert "envoi" not in result
    assert "rapide" not in result
    assert "neuf" not in result
    # Max 8 mots
    long_title = "Pokemon Card One Two Three Four Five Six Seven Eight Nine Ten"
    r3 = q(long_title)
    assert len(r3.split()) <= 8

test("Market price query cleaning", test_clean_query)

def test_parse_ebay_prices():
    from market_price import MarketPriceEstimator
    est = MarketPriceEstimator(min_samples=1)
    # Simuler du HTML eBay
    html = """
    <div class="s-item">
        <h3 class="s-item__title">Pokemon Card Pikachu</h3>
        <span class="s-item__price">EUR 25,50</span>
    </div>
    <div class="s-item">
        <h3 class="s-item__title">Pokemon Card Charizard</h3>
        <span class="s-item__price">EUR 42,00</span>
    </div>
    <div class="s-item">
        <h3 class="s-item__title">Pokemon Card Mewtwo</h3>
        <span class="s-item__price">EUR 18,90</span>
    </div>
    """
    prices = est._parse_ebay_prices(html)
    assert len(prices) == 3, f"Expected 3 prices, got {len(prices)}: {prices}"
    assert 25.5 in prices
    assert 42.0 in prices
    assert 18.9 in prices

test("eBay price HTML parsing", test_parse_ebay_prices)

def test_parse_ebay_range_prices():
    from market_price import MarketPriceEstimator
    est = MarketPriceEstimator(min_samples=1)
    html = """
    <div class="s-item">
        <h3 class="s-item__title">Shop on eBay</h3>
        <span class="s-item__price">EUR 5,00</span>
    </div>
    <div class="s-item">
        <h3 class="s-item__title">Card lot</h3>
        <span class="s-item__price">EUR 10,00 to EUR 20,00</span>
    </div>
    """
    prices = est._parse_ebay_prices(html)
    # Le premier item "Shop on eBay" doit être ignoré
    assert len(prices) == 1, f"Expected 1 price (range avg), got {len(prices)}: {prices}"
    assert abs(prices[0] - 15.0) < 0.01  # Moyenne du range

test("eBay range price + Shop on eBay filter", test_parse_ebay_range_prices)


# ════════════════════════════════════════
# 5. ALERTER
# ════════════════════════════════════════
print("\n📢 TEST ALERTER")

def test_alerter_dry_run():
    from config import AlertConfig
    from alerter import Alerter
    from scorer import Deal
    from vinted_api import VintedItem
    from market_price import MarketData

    alerter = Alerter(AlertConfig(), dry_run=True)

    item = VintedItem(
        item_id="42", title="Charizard VMAX Secret",
        price=25.0, currency="EUR", brand="Pokemon",
        size="", url="https://vinted.fr/items/42",
        photo_url="https://example.com/photo.jpg",
        user_login="seller", country="FR", status="Active",
    )
    market = MarketData(
        median_price=80.0, min_price=60.0, max_price=100.0,
        sample_count=12, source="ebay",
        prices=[60,65,70,75,78,80,82,85,88,90,95,100],
        query_used="charizard vmax secret"
    )
    deal = Deal(
        item=item, market=market,
        buy_total=28.0, sell_net=60.0, profit=32.0,
        margin=1.14, confidence="high", score=85.0,
    )

    success = alerter.send_deal(deal)
    assert success == True
    assert alerter.sent_count == 1

test("Alerter dry-run deal formatting", test_alerter_dry_run)


# ════════════════════════════════════════
# 6. LOGGER
# ════════════════════════════════════════
print("\n📋 TEST LOGGER")

def test_logger_json():
    from logger import setup_logger
    import io
    log = setup_logger("test_json", level="DEBUG", json_output=True)
    # Should not crash
    log.info("Test message", extra={"keyword": "pokemon", "items_scraped": 15})
    log.warning("Test warning")

test("JSON logger output", test_logger_json)


# ════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════
print(f"\n{'='*50}")
print(f"RÉSULTAT: {PASS} passed, {FAIL} failed")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
