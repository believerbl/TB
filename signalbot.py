import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, error
import time
import pandas as pd

# Load environment variables
load_dotenv(".env")
load_dotenv("ini.env")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Configuration
PAIRS = ["EUR/USD", "EUR/JPY", "EUR/GBP"]
UPDATE_INTERVAL = 60  # 60 seconds
HISTORY_LENGTH = 100  # Number of periods to keep

class ForexSignalBot:
    def __init__(self):
        print("Initializing Forex Signal Bot...")
        self.bot = None
        self.session = None
        self.running = True
        self.price_history = {pair: {'close': []} for pair in PAIRS}
        self.last_api_call = 0
        self.api_calls = 0
        
        if TELEGRAM_TOKEN:
            try:
                self.bot = Bot(token=TELEGRAM_TOKEN)
                print("Telegram bot initialized")
            except Exception as e:
                print(f"Telegram bot initialization failed: {e}")

    async def verify_chat_id(self):
        """Verify the Telegram chat ID is valid"""
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

    async def api_request(self, pair):
        """Handle API requests with rate limiting"""
        now = time.time()
        if now - self.last_api_call < 8:
            await asyncio.sleep(8 - (now - self.last_api_call))
        
        self.last_api_call = time.time()
        self.api_calls += 1
        
        url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval=1min&outputsize={HISTORY_LENGTH}&apikey={API_KEY}"
        try:
            async with self.session.get(url, timeout=10) as response:
                data = await response.json()
                if response.status == 200 and 'values' in data:
                    return data['values']
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
        """Fetch OHLC data for all pairs"""
        prices = {}
        errors = 0
        
        for pair in PAIRS:
            data = await self.api_request(pair)
            if data is not None:
                close_prices = [float(item['close']) for item in data]
                self.price_history[pair]['close'] = close_prices
                prices[pair] = close_prices[-1]  # Latest price
            else:
                prices[pair] = None
                errors += 1
        
        if errors == len(PAIRS):
            print("All API requests failed - possible API issue")
            await asyncio.sleep(60)
            
        return prices

    def analyze_pair(self, pair):
        """Generate trading signals using pure pandas"""
        close_prices = self.price_history[pair]['close']
        if len(close_prices) < 20:  # Need enough data
            return None
        
        close = pd.Series(close_prices)
        
        # Calculate indicators
        sma_20 = close.rolling(20).mean().iloc[-1]
        sma_50 = close.rolling(50).mean().iloc[-1]
    
        # Simple trend detection
        current_price = close.iloc[-1]
        prev_price = close.iloc[-2]
    
        if current_price > sma_20 and current_price > sma_50 and current_price > prev_price:
            signal = "BUY"
        elif current_price < sma_20 and current_price < sma_50 and current_price < prev_price:
            signal = "SELL"
        else:
            signal = "FLAT"
        
        return {
            'signal': signal,
            'price': current_price,
            'sma_20': sma_20,
            'sma_50': sma_50
        }

    def format_signal_message(self, signals):
        """Create formatted signal message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = [f"🚀 *Forex Trading Signals* ({timestamp})"]
        message.append("```")
        
        for pair, analysis in signals.items():
            if not analysis or not analysis['signal']:
                continue
                
            entry = analysis['price']
            stop_loss = entry * 0.995 if analysis['signal'] == "BUY" else entry * 1.005
            take_profit = entry * 1.005 if analysis['signal'] == "BUY" else entry * 0.995
            
            message.append(
                f"{pair} {analysis['signal']}\n"
                f"Entry: {entry:.5f}\n"
                f"SL: {stop_loss:.5f}\n"
                f"TP: {take_profit:.5f}\n"
                f"SMA20: {analysis['sma_20']:.5f}\n"
                f"SMA50: {analysis['sma_50']:.5f}\n"
            )
        
        if len(message) == 2:  # Only header and code block marker
            return None
            
        message.append("```")
        message.append("⚠️ *Disclaimer*: Signals are for educational purposes only")
        return "\n".join(message)

    async def send_to_telegram(self, message):
        """Safe message sending to Telegram"""
        if not self.bot or not message:
            return
            
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='Markdown',
                disable_notification=False
            )
        except error.BadRequest:
            print(f"Message not sent - invalid CHAT_ID: {CHAT_ID}")
        except Exception as e:
            print(f"Telegram send error: {type(e).__name__}")

    async def start(self):
        """Start signal generation"""
        telegram_ok = await self.verify_chat_id() if TELEGRAM_TOKEN else False
        self.session = aiohttp.ClientSession()
        
        if telegram_ok:
            await self.send_to_telegram("🚀 Forex Signal Bot Started")
        
        while self.running:
            try:
                prices = await self.get_market_data()
                signals = {}
                
                for pair in PAIRS:
                    signals[pair] = self.analyze_pair(pair)
                
                message = self.format_signal_message(signals)
                if message:
                    print(f"Generated signals at {datetime.now()}")
                    await self.send_to_telegram(message)
                else:
                    print(f"No signals generated at {datetime.now()}")
                    
                await asyncio.sleep(UPDATE_INTERVAL)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Unexpected error: {type(e).__name__}: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Clean shutdown"""
        print("\nStopping bot...")
        self.running = False
        if self.session:
            await self.session.close()
        if self.bot and CHAT_ID:
            await self.send_to_telegram("🛑 Forex Signal Bot Stopped")

async def main():
    bot = ForexSignalBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
    print("Bot shutdown complete")

if __name__ == "__main__":
    print(f"Starting Forex Signal Bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.run(main())