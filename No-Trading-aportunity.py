import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import time
import pandas as pd
import pandas_ta as ta

# Load environment variables
load_dotenv("ini.env")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")
TRADING_PAIRS = os.getenv("TRADING_PAIRS", "EUR/USD,USD/JPY,GBP/USD").split(",")

# Configuration
TIMEFRAME = "1min"
UPDATE_INTERVAL = 60  # Seconds
HISTORY_LENGTH = 100
RSI_PERIOD = 14
RSI_OVERBOUGHT = 50
RSI_OVERSOLD = 40
MIN_PRICE_CHANGE = 0.5  # 0.5%
RATE_LIMIT = 6  # Requests per minute

class OTCTradingBot:
    def __init__(self):
        if not API_KEY:
            raise ValueError("API key not found in environment variables")

        print("Initializing OTC Trading Bot...")
        self.bot = None
        self.session = None
        self.running = True
        self.price_history = {pair: {'close': []} for pair in TRADING_PAIRS}
        self.last_api_call = 0
        self.api_calls = 0
        self.last_prediction = {}

        if TELEGRAM_TOKEN:
            try:
                self.bot = Bot(token=TELEGRAM_TOKEN)
                print("Telegram bot initialized")
            except Exception as e:
                print(f"Telegram bot initialization failed: {e}")

    async def verify_chat_id(self):
        try:
            if CHAT_ID:
                await self.bot.send_message(chat_id=CHAT_ID, text="✅ Trading Bot Started Successfully!")
                print(f"📨 Startup confirmation sent to chat ID {CHAT_ID}")
        except TelegramError as e:
            print(f"Chat ID verification failed: {e}")

    async def api_request(self, endpoint, params=None):
        try:
            now = time.time()
            if now - self.last_api_call < 60 and self.api_calls >= RATE_LIMIT:
                wait_time = 60 - (now - self.last_api_call)
                print(f"⏳ Rate limit reached. Waiting {wait_time:.1f} seconds")
                await asyncio.sleep(wait_time)
                self.api_calls = 0

            async with self.session.get(
                f"https://api.twelvedata.com/{endpoint}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                self.last_api_call = time.time()
                self.api_calls += 1

                if response.status != 200:
                    error = await response.text()
                    print(f"API Error {response.status}: {error}")
                    return None

                data = await response.json()
                if 'code' in data and data['code'] != 200:
                    print(f"API Error {data['code']}: {data.get('message')}")
                    return None

                return data

        except asyncio.TimeoutError:
            print("⌛ API request timed out")
        except Exception as e:
            print(f"🌐 Network Error: {str(e)}")
        return None

    async def get_market_data(self, pair, history=False):
        """
        Fetch multiple bars if history=True to seed price_history;
        otherwise fetch only the latest bar and update history.
        """
        formatted = f"{pair}:FOREX"
        params = {
            "symbol": formatted,
            "interval": TIMEFRAME,
            "apikey": API_KEY,
            "outputsize": HISTORY_LENGTH if history else 1
        }
        print(f"📡 Fetching {'history' if history else 'latest'} data for {formatted}…")
        data = await self.api_request("time_series", params)
        if not data or "values" not in data:
            print(f"❌ No time_series data for {formatted}")
            return None

        bars = data["values"]
        # Bars are sorted newest-first
        latest_bar = bars[0]
        price = float(latest_bar["close"])
        ts = datetime.fromisoformat(latest_bar["datetime"])

        if history:
            # Seed full history in chronological order
            closes = [float(bar["close"]) for bar in reversed(bars)]
            self.price_history[pair]["close"] = closes
            print(f"✅ Seeded {len(closes)} historical bars for {pair}")
        else:
            # Rolling update
            self.price_history[pair]["close"].append(price)
            if len(self.price_history[pair]["close"]) > HISTORY_LENGTH:
                self.price_history[pair]["close"].pop(0)

        print(f"✅ {pair} @ {ts} = {price}")
        return {"close": price, "pair": pair, "timestamp": ts}

    def analyze_pair(self, pair):
        close_prices = self.price_history[pair]['close']
        if len(close_prices) < RSI_PERIOD + 1:
            print(f"⚠️ Insufficient data for {pair} ({len(close_prices)}/{RSI_PERIOD+1})")
            return None

        try:
            series = pd.Series(close_prices)
            rsi = ta.rsi(close=series, length=RSI_PERIOD)
            if rsi is None or rsi.empty:
                return None

            current_rsi = round(rsi.iloc[-1], 2)
            previous_rsi = round(rsi.iloc[-2], 2) if len(rsi) > 1 else current_rsi

            current_price = close_prices[-1]
            price_change = abs((current_price - close_prices[-2]) / close_prices[-2] * 100) if len(close_prices) > 1 else 0

            signal = None
            #if price_change >= MIN_PRICE_CHANGE:
            if current_rsi <= RSI_OVERSOLD and previous_rsi > RSI_OVERSOLD:
                signal = "CALL"
            elif current_rsi >= RSI_OVERBOUGHT and previous_rsi < RSI_OVERBOUGHT:
                signal = "PUT"

            print(f"📊 {pair} Analysis: RSI {current_rsi} | Δ {price_change:.2f}%")
            return {
                'signal': signal or 'None',
                'price': current_price,
                'rsi': current_rsi,
                'timeframe': TIMEFRAME,
                'timestamp': datetime.now()
            }

        except Exception as e:
            print(f"Analysis error for {pair}: {e}")
            return None

    async def start(self):
        self.session = aiohttp.ClientSession()
        print("Bot started successfully")
        await self.verify_chat_id()

        # Seed history for each pair before main loop
        for pair in TRADING_PAIRS:
            await self.get_market_data(pair, history=True)

        while self.running:
            try:
                print(f"\n🔁 Cycle started at {datetime.now().strftime('%H:%M:%S')}")
                for pair in TRADING_PAIRS:
                    data = await self.get_market_data(pair, history=False)
                    if data:
                        analysis = self.analyze_pair(pair)
                        
                        if analysis:
                            try:
                                rsi_series = ta.rsi(pd.Series(self.price_history[pair]['close']), length=RSI_PERIOD)
                                prev_rsi = rsi_series.iloc[-2] if len(rsi_series) > 1 else analysis['rsi']
                                print(
                                    f"📈 [{pair}] RSI Info:\n"
                                    f"  ➤ Current RSI: {analysis['rsi']:.2f}\n"
                                    f"  ➤ Previous RSI: {prev_rsi:.2f}"
                                )
                            except Exception as e:
                                print(f"⚠️ Error getting RSI info for {pair}: {e}")
                        

                        if analysis:
                            await self.send_signal(analysis, pair)
                            if analysis['signal'] != 'None':
                                self.last_prediction[pair] = analysis

                print(f"⏳ Waiting {UPDATE_INTERVAL} seconds for next update...")
                await asyncio.sleep(UPDATE_INTERVAL)

            except Exception as e:
                print(f"Main loop error: {e}")
                await asyncio.sleep(5)

    async def send_signal(self, analysis, pair):
        if analysis['signal'] == 'None':
            message = (
                f"🔄 No Trading Opportunity\n"
                f"*Pair*: {pair}\n"
                f"*Time*: {analysis['timestamp'].strftime('%H:%M')}\n"
                f"*RSI*: {analysis['rsi']:.2f}\n"
                f"*Price*: {analysis['price']:.4f}"
            )
        else:
            message = (
                f"🚨 *{analysis['signal']} Signal Alert* 🚨\n"
                f"*Pair*: {pair}\n"
                f"*Time*: {analysis['timestamp'].strftime('%H:%M')}\n"
                f"*RSI*: {analysis['rsi']:.2f}\n"
                f"*Price*: {analysis['price']:.4f}\n"
                f"*Timeframe*: {analysis['timeframe']}\n"
                f"*Expiry Window*: 5-15 minutes\n\n"
                f"⚠️ *Risk Management Recommended*"
            )
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            print(f"📨 Signal sent for {pair} at {analysis['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"Failed to send Telegram message: {e}")

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()
        print("🛑 Bot stopped successfully")

async def main():
    bot = OTCTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n🛑 Received keyboard interrupt, stopping...")
    finally:
        await bot.stop()

if __name__ == "__main__":
    print(f"⏱ Starting OTC Trading Bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📈 Monitoring pairs: {TRADING_PAIRS}")
    asyncio.run(main())
