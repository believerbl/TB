import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
import time
import pandas as pd
try:
    import pandas_ta_classic as ta
except ImportError:
    import pandas_ta as ta

# Load environment variables
load_dotenv(".env")
load_dotenv("ini.env")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")
TRADING_PAIRS = os.getenv("TRADING_PAIRS", "EURUSD,USDJPY").split(",")  # Updated format

# Configuration
TIMEFRAME = "1min"
UPDATE_INTERVAL = 60  # Seconds
HISTORY_LENGTH = 100
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MIN_PRICE_CHANGE = 0.5  # 0.5%
RATE_LIMIT = 6  # Reduced for free tier safety

class OTCTradingBot:
    def __init__(self):
        if not API_KEY or API_KEY.startswith("your_api_key"):
            raise ValueError("Invalid Twelve Data API key - get one from https://twelvedata.com/pricing")

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

    async def api_request(self, endpoint, params=None):
        try:
            now = time.time()
            if now - self.last_api_call < 60 and self.api_calls >= RATE_LIMIT:
                wait_time = 60 - (now - self.last_api_call)
                print(f"Rate limit reached. Waiting {wait_time:.1f} seconds")
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
            print("API request timed out")
        except Exception as e:
            print(f"Network Error: {str(e)}")
        return None

    async def get_market_data(self, pair):
        try:
            params = {
                "symbol": pair,
                "interval": TIMEFRAME,
                "apikey": API_KEY,
                "country": "United States"
            }
            
            data = await self.api_request("price", params)
            if not data or 'price' not in data:
                print(f"Invalid data for {pair}: {data}")
                return None

            return {
                "close": float(data['price']),
                "pair": pair,
                "timestamp": datetime.now()
            }

        except Exception as e:
            print(f"Error processing {pair}: {e}")
            return None

    def analyze_pair(self, pair):
        close_prices = self.price_history[pair]['close']
        if len(close_prices) < RSI_PERIOD + 1:
            return None

        try:
            series = pd.Series(close_prices)
            rsi = series.ta.rsi(length=RSI_PERIOD)
            if rsi is None or rsi.empty:
                return None
                
            current_rsi = round(rsi.iloc[-1], 2)
            previous_rsi = round(rsi.iloc[-2], 2) if len(rsi) > 1 else current_rsi

            current_price = close_prices[-1]
            price_change = 0
            
            if len(close_prices) > 1:
                price_change = abs((current_price - close_prices[-2]) / close_prices[-2] * 100)

            signal = None
            if price_change >= MIN_PRICE_CHANGE:
                if current_rsi <= RSI_OVERSOLD and previous_rsi > RSI_OVERSOLD:
                    signal = "CALL"
                elif current_rsi >= RSI_OVERBOUGHT and previous_rsi < RSI_OVERBOUGHT:
                    signal = "PUT"

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
        
        while self.running:
            try:
                for pair in TRADING_PAIRS:
                    data = await self.get_market_data(pair)
                    if data:
                        self.price_history[pair]['close'].append(data['close'])
                        if len(self.price_history[pair]['close']) > HISTORY_LENGTH:
                            self.price_history[pair]['close'].pop(0)
                        
                        analysis = self.analyze_pair(pair)
                        if analysis:
                            await self.send_signal(analysis, pair)
                
                await asyncio.sleep(UPDATE_INTERVAL)
                
            except Exception as e:
                print(f"Main loop error: {e}")
                await asyncio.sleep(5)

    async def send_signal(self, analysis, pair):
        if analysis['signal'] == 'None':
            message = (
                f"🔄 NO SIGNAL 🔄\n"
                f"Pair: {pair}\n"
                f"Time: {analysis['timestamp'].strftime('%H:%M')}\n"
                f"RSI: {analysis['rsi']:.2f}\n"
                f"Price: {analysis['price']:.4f}"
            )
        else:
            message = (
                f"🚨 SIGNAL: {analysis['signal']} 🚨\n"
                f"Pair: {pair}\n"
                f"Time: {analysis['timestamp'].strftime('%H:%M')}\n"
                f"RSI: {analysis['rsi']:.2f}\n"
                f"Price: {analysis['price']:.4f}\n"
                f"Expiry: 5-15 mins"
            )
        
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode="Markdown"
            )
            print(f"Sent {analysis['signal']} signal for {pair}")
        except Exception as e:
            print(f"Failed to send message: {e}")

    async def stop(self):
        self.running = False
        if self.session:
            await self.session.close()
        print("Bot stopped successfully")

async def main():
    bot = OTCTradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()

if __name__ == "__main__":
    print(f"Starting Bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Monitoring: {TRADING_PAIRS}")
    asyncio.run(main())