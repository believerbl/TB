import asyncio
import argparse
import logging
from datetime import datetime
import sys

from src.config import settings
from src.database.models import init_db
from src.data_feed.twelve_data import TwelveDataFeed
from src.data_feed.replay_feed import ReplayFeed
from src.strategy.indicators import IndicatorEngine
from src.strategy.confluence import ConfluenceScorer
from src.tracker.outcome_eval import TradeOutcomeEvaluator
from src.notifier.telegram_bot import TelegramNotifier

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_activity.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("MainRunner")

async def market_scanner(data_feed, tracker, notifier, watchlist):
    """Continuous async loop that scans assets round-robin (1 symbol per cycle with 60s gap)."""
    last_signal_time = {symbol: None for symbol in watchlist}
    current_idx = 0
    
    logger.info(f"Market scanner started (Round-Robin mode). Monitoring: {watchlist}")
    
    while True:
        if not watchlist:
            await asyncio.sleep(10)
            continue

        symbol = watchlist[current_idx % len(watchlist)]
        current_idx = (current_idx + 1) % len(watchlist)

        try:
            logger.info(f"Scanning symbol: {symbol}")
            # 1. Fetch Market Data for a single symbol (1 API credit per call)
            df = await data_feed.fetch_candles(
                symbol=symbol,
                interval=settings.TIMEFRAME,
                n_bars=max(settings.HISTORY_LENGTH, 250)
            )

            if df is not None and not df.empty:
                try:
                    # 2. Enrich with Confluence Indicators
                    enriched = IndicatorEngine.build_indicators(df)
                    latest_row = enriched.iloc[-1]
                    current_time = latest_row['datetime']

                    # 3. Analyze for Signals
                    signal = ConfluenceScorer.analyze(latest_row)

                    # 4. Execute Signal (Prevent duplicate alerts on the same candle)
                    if signal['signal_type'] != 'NEUTRAL' and last_signal_time.get(symbol) != current_time:
                        logger.info(f"🔥 {signal['signal_type']} Signal on {symbol} at {signal['price']} (Confidence: {signal['confidence']}%)")

                        # Log to database as PENDING
                        tracker.log_signal(symbol, signal['signal_type'], signal['price'], signal['confidence'])

                        # Dispatch to Telegram
                        await notifier.broadcast_signal(signal, symbol)

                        # Update cache to prevent spam
                        last_signal_time[symbol] = current_time

                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}")

        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")

        # 5. Evaluate expired pending trades from previous cycles
        try:
            await tracker.evaluate_pending_trades()
        except Exception as e:
            logger.error(f"Error evaluating pending trades: {e}")

        # 6. Sleep before next cycle (10 seconds for demo pacing, settings.UPDATE_INTERVAL for live)
        sleep_time = 10 if settings.DEMO_MODE else settings.UPDATE_INTERVAL
        await asyncio.sleep(sleep_time)


async def main():
    # 1. Parse CLI Arguments for Presentation Failsafe
    parser = argparse.ArgumentParser(description="TB-Project Trading Engine")
    parser.add_argument('--live', action='store_true', help="Run using live Twelve Data API")
    args = parser.parse_args()

    # Default to DEMO mode for safety unless --live is passed
    settings.DEMO_MODE = not args.live

    # 2. Initialize Infrastructure
    init_db(settings.DB_PATH)
    
    if settings.DEMO_MODE:
        logger.info("Initializing DEMO Mode (Offline Replay).")
        data_feed = ReplayFeed('data/historical/eurusd_sample.csv')
        watchlist = ['EUR/USD']
    else:
        logger.info("Initializing LIVE Mode (Twelve Data Batch API).")
        data_feed = TwelveDataFeed()
        watchlist = settings.TRADING_PAIRS
        
    tracker = TradeOutcomeEvaluator(data_feed)
    notifier = TelegramNotifier(data_feed, tracker)

    # 3. Build & Start Telegram App
    telegram_app = notifier.build()
    if telegram_app:
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        logger.info("Telegram interface online.")
    else:
        logger.warning("Telegram Bot Token not configured. Running headless engine mode.")

    # 4. Start Market Scanner Loop
    scanner_task = asyncio.create_task(market_scanner(data_feed, tracker, notifier, watchlist))

    try:
        # Keep main event loop running forever
        await scanner_task
    except asyncio.CancelledError:
        logger.info("Shutting down engine...")
    finally:
        if telegram_app and telegram_app.updater:
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete.")
