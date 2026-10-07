import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import time
import pandas as pd

# Load environment variables
load_dotenv("ini.env")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")
TRADING_PAIRS = os.getenv("TRADING_PAIRS", "USD/PKR,USD/ARS").split(",")

# Configuration
TIMEFRAME = "1min"
UPDATE_INTERVAL = 60
HISTORY_LENGTH = 100

class OTCTradingBot:
    def __init__(self):
        print("Initializing OTC Trading Bot...")
        self.bot = None
        self.session = None
        self.running = True
        self.price_history = {pair: {'close': []} for pair in TRADING_PAIRS}
        self.last_api_call = 0
        self.api_calls = 0
        self.last_prediction = {}  # Stores the last prediction for each pair

        if TELEGRAM_TOKEN:
            try:
                self.bot = Bot(token=TELEGRAM_TOKEN)
                print("Telegram bot initialized")
            except Exception as e:
                print(f"Telegram bot initialization failed: {e}")

    async def verify_chat_id(self):
        if not self.bot or not CHAT_ID:
            return False
        try:
            msg = await self.bot.send_message(
                chat_id=CHAT_ID,
                text="🔍 Connection test (this will be deleted)",
                disable_notification=True
            )
            await self.bot.delete_message(chat_id=CHAT_ID, message_id=msg.message_id)
            return True
        except error.Unauthorized:
            print("❌ Bot is not authorized to access this chat/channel")
        except error.BadRequest as e:
            print(f"❌ Invalid CHAT_ID format: {e}")
        except error.ChatNotFound:
            print("❌ Chat/channel not found - ensure bot was added as admin")
        except Exception as e:
            print(f"Telegram verification error: {type(e).__name__}: {e}")
        return False

    async def api_request(self, pair, endpoint="time_series"):
        now = time.time()
        if now - self.last_api_call < 8:
            await asyncio.sleep(8 - (now - self.last_api_call))

        self.last_api_call = time.time()
        self.api_calls += 1

        if endpoint == "time_series":
            url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval={TIMEFRAME}&outputsize={HISTORY_LENGTH}&apikey={API_KEY}"
        elif endpoint == "price":
            url = f"https://api.twelvedata.com/price?symbol={pair}&apikey={API_KEY}"

        try:
            async with self.session.get(url, timeout=10) as response:
                data = await response.json()
                if response.status == 200:
                    return data
                elif response.status == 429:
                    print("⚠️ API rate limit exceeded - waiting 60 seconds")
                    await asyncio.sleep(60)
                    return None
                else:
                    print(f"API error for {pair}: {data.get('message', 'No error message')}")
                    return None
        except asyncio.TimeoutError:
            print(f"Timeout getting {pair}")
            return None
        except Exception as e:
            print(f"Error getting {pair}: {type(e).__name__} - {str(e)}")
            return None

    async def get_market_data(self):
        prices = {}
        errors = 0

        for pair in TRADING_PAIRS:
            data = await self.api_request(pair)
            if data is not None and 'values' in data:
                close_prices = [float(item['close']) for item in data['values']]
                self.price_history[pair]['close'] = close_prices
                prices[pair] = close_prices[-1]  # Latest price
            else:
                prices[pair] = None
                errors += 1

        if errors == len(TRADING_PAIRS):
            print("All API requests failed - possible API issue")
            await asyncio.sleep(60)

        return prices

    def analyze_pair(self, pair):
        close_prices = self.price_history[pair]['close']
        if len(close_prices) < 5:
            return None

        close = pd.Series(close_prices)
        current_price = close.iloc[-1]
        prev_price = close.iloc[-2]

        return {
            'signal': "CALL" if current_price > prev_price else "PUT",
            'price': current_price,
            'timeframe': TIMEFRAME,
            'timestamp': datetime.now()
        }

    def check_prediction_outcome(self, pair, prediction, current_price):
        """Check the last prediction's result using the latest price (no API call)."""
        if prediction['signal'] == "CALL":
            result = "WIN ✅" if current_price > prediction['price'] else "LOSS ❌"
        else:
            result = "WIN ✅" if current_price < prediction['price'] else "LOSS ❌"

        return (
            f"🔄 *RESULT* 🔄\n\n"
            f"{pair.replace('/', '')}-OTCq\n"
            f"Predicted: {prediction['signal']} at {prediction['price']:.4f}\n"
            f"Actual: {current_price:.4f}\n"
            f"Result: {result}"
        )

    def format_signal_message(self, signals):
        timestamp = datetime.now().strftime("%H:%M")
        messages = []

        for pair, analysis in signals.items():
            if not analysis or not analysis['signal']:
                continue

            display_pair = pair.replace("/", "")
            message = (
                f"🚀 *SIGNAL* 🚀\n\n"
                f"{display_pair}-OTCq\n"
                f"{timestamp}\n"
                f"{analysis['timeframe']}\n"
                f"*{analysis['signal']}*\n\n"
                f"UTC +5.00 / MT4 Server\n"
                f"https://t.me/joinchat/example\n"
            )
            messages.append(message)

        return "\n".join(messages) if messages else None

    async def send_to_telegram(self, message):
        if not self.bot or not message:
            return
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='Markdown',
                disable_notification=False
            )
            print(f"📨 Telegram message sent at {datetime.now().strftime('%H:%M:%S')}")
        except error.BadRequest:
            print(f"Message not sent - invalid CHAT_ID: {CHAT_ID}")
        except Exception as e:
            print(f"Telegram send error: {type(e).__name__}")

    async def start(self):
        telegram_ok = await self.verify_chat_id() if TELEGRAM_TOKEN else False
        self.session = aiohttp.ClientSession()

        if telegram_ok:
            await self.send_to_telegram("🚀 OTC Trading Bot Started")

        while self.running:
            try:
                # 1. Fetch latest market data (single API call per pair)
                prices = await self.get_market_data()
                signals = {}
                results = []

                # 2. For each pair:
                for pair in TRADING_PAIRS:
                    current_price = prices[pair]
                    if current_price is None:
                        continue

                    # A. Check last prediction's result (if exists)
                    if pair in self.last_prediction:
                        result_msg = self.check_prediction_outcome(
                            pair, 
                            self.last_prediction[pair], 
                            current_price
                        )
                        results.append(result_msg)

                    # B. Generate new signal
                    signals[pair] = self.analyze_pair(pair)
                    if signals[pair]:
                        self.last_prediction[pair] = signals[pair]  # Store for next cycle

                # 3. Send all messages
                if results:
                    await self.send_to_telegram("\n\n".join(results))
                
                signal_message = self.format_signal_message(signals)
                if signal_message:
                    await self.send_to_telegram(signal_message)

                await asyncio.sleep(UPDATE_INTERVAL)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Unexpected error: {type(e).__name__}: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        print("\nStopping bot...")
        self.running = False
        if self.session:
            await self.session.close()
        if self.bot and CHAT_ID:
            await self.send_to_telegram("🛑 OTC Trading Bot Stopped")

async def main():
    bot = OTCTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
    print("Bot shutdown complete")

if __name__ == "__main__":
    print(f"\u23f1\ufe0f Starting OTC Trading Bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\U0001f4ca Monitoring pairs: {TRADING_PAIRS}")
    asyncio.run(main())