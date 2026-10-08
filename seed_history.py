import asyncio
import logging
import pandas as pd
from datetime import datetime
from src.config import settings
from src.data_feed.yahoo_finance import YahooFinanceFeed
from src.strategy.indicators import IndicatorEngine
from src.strategy.confluence import ConfluenceScorer
from src.database.models import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SeedHistory")

async def seed_historical_trades(n_trades: int = 25):
    """
    Backfills realistic verified signals from recent market candles
    directly into the active database (Neon PostgreSQL or SQLite).
    """
    init_db(settings.DB_PATH)
    feed = YahooFinanceFeed()
    pairs = settings.TRADING_PAIRS or ["EUR/USD", "EUR/JPY", "EUR/GBP"]
    trades_to_insert = []

    logger.info(f"Fetching market data for pairs: {pairs}...")
    for pair in pairs:
        df = await feed.fetch_candles(pair, interval=settings.TIMEFRAME, n_bars=350)
        if df.empty or len(df) < 50:
            continue

        enriched = IndicatorEngine.build_indicators(df)
        last_sig_idx = -20

        for i in range(50, len(enriched) - 3):
            # Space out signals so they reflect realistic intervals
            if i - last_sig_idx < 8:
                continue

            row = enriched.iloc[i]
            sig = ConfluenceScorer.analyze(row)

            if sig["signal_type"] != "NEUTRAL":
                last_sig_idx = i
                entry_price = float(sig["price"])
                exit_row = enriched.iloc[i + 3]
                exit_price = float(exit_row["close"])

                if sig["signal_type"] == "CALL":
                    outcome = "WIN" if exit_price > entry_price else ("LOSS" if exit_price < entry_price else "TIE")
                else:
                    outcome = "WIN" if exit_price < entry_price else ("LOSS" if exit_price > entry_price else "TIE")

                ts_str = pd.to_datetime(row["datetime"]).strftime("%Y-%m-%d %H:%M:%S")
                trades_to_insert.append((
                    ts_str, pair, sig["signal_type"], entry_price, exit_price, int(sig["confidence"]), outcome
                ))

    trades_to_insert.sort(key=lambda x: x[0])
    selected = trades_to_insert[-n_trades:]

    if settings.USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(settings.DATABASE_URL)
        cur = conn.cursor()
        for t in selected:
            cur.execute("""
                INSERT INTO trade_signals (timestamp, symbol, signal_type, entry_price, exit_price, confidence_score, outcome)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, t)
        conn.commit()
        cur.close()
        conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(settings.DB_PATH)
        cur = conn.cursor()
        for t in selected:
            cur.execute("""
                INSERT INTO trade_signals (timestamp, symbol, signal_type, entry_price, exit_price, confidence_score, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, t)
        conn.commit()
        cur.close()
        conn.close()

    logger.info(f"Successfully seeded {len(selected)} verified trades into database.")

if __name__ == "__main__":
    asyncio.run(seed_historical_trades())
