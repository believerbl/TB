import os
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from telegram import Bot, error
import time

# Load environment variables
load_dotenv(".env")
load_dotenv("ini.env")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Configuration
PAIRS = ["EUR/USD", "EUR/JPY", "EUR/GBP"]
UPDATE_INTERVAL = 60  # 60 seconds to stay within free tier limits
MAX_RETRIES = 2
API_TIMEOUT = 10
ERROR_COOLDOWN = 60  # Wait 60 seconds after API errors

class LivePriceBot:
    def __init__(self):
        print("Initializing Real-Time Price Bot...")
        self.bot = None
        self.session = None
        self.running = True
        self.price_history = {pair: [] for pair in PAIRS}
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
            # Try sending a test message and deleting it
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
        """Handle API requests with rate limiting and retries"""
        # Rate limiting for free tier (8 requests/minute)
        now = time.time()
        if now - self.last_api_call < 8:
            await asyncio.sleep(8 - (now - self.last_api_call))
        
        self.last_api_call = time.time()
        self.api_calls += 1
        
        url = f"https://api.twelvedata.com/price?symbol={pair}&apikey={API_KEY}"
        try:
            async with self.session.get(url, timeout=API_TIMEOUT) as response:
                data = await response.json()
                if response.status == 200 and 'price' in data and data['price']:
                    return float(data['price'])
                elif response.status == 429:
                    print("⚠️ API rate limit exceeded - waiting 60 seconds")
                    await asyncio.sleep(ERROR_COOLDOWN)
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

    async def get_live_prices(self):
        """Fetch live prices with enhanced error handling"""
        prices = {}
        errors = 0
        
        for pair in PAIRS:
            price = await self.api_request(pair)
            if price is not None:
                prices[pair] = price
                self.update_price_history(pair, price)
            else:
                prices[pair] = None
                errors += 1
        
        if errors == len(PAIRS):
            print("All API requests failed - possible API issue")
            await asyncio.sleep(ERROR_COOLDOWN)
            
        return prices

    def update_price_history(self, pair, price):
        """Maintain price history for trends"""
        self.price_history[pair].append(price)
        if len(self.price_history[pair]) > 100:
            self.price_history[pair].pop(0)

    def format_message(self, prices):
        """Create formatted output with proper alignment"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        lines = [f"📊 Live Prices ({timestamp})"]
        
        max_len = max(len(pair) for pair in PAIRS)
        for pair in PAIRS:
            price = prices.get(pair)
            if price is None:
                lines.append(f"{pair.ljust(max_len)}: ❌ Error")
                continue
                
            trend = self.get_trend_arrow(pair, price)
            decimals = 4 if "JPY" not in pair else 2
            lines.append(f"{trend} {pair.ljust(max_len)}: {price:.{decimals}f}")
            
        return "\n".join(lines)

    def get_trend_arrow(self, pair, current_price):
        """Determine trend arrow"""
        history = self.price_history[pair]
        if len(history) < 2:
            return "↔"
        return "↑" if current_price > history[-2] else "↓"

    async def send_to_telegram(self, message):
        """Safe message sending to Telegram"""
        if not self.bot:
            return
            
        try:
            await self.bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                disable_notification=True
            )
        except error.BadRequest:
            print(f"Message not sent - invalid CHAT_ID: {CHAT_ID}")
        except Exception as e:
            print(f"Telegram send error: {type(e).__name__}")

    async def start(self):
        """Start live price updates"""
        telegram_ok = await self.verify_chat_id() if TELEGRAM_TOKEN else False
        self.session = aiohttp.ClientSession()
        
        if telegram_ok:
            await self.send_to_telegram("🚀 Live Price Bot Started (60s updates)")
        
        while self.running:
            try:
                prices = await self.get_live_prices()
                message = self.format_message(prices)
                print(message)
                
                if telegram_ok and any(prices[pair] is not None for pair in PAIRS):
                    await self.send_to_telegram(message)
                    
                await asyncio.sleep(UPDATE_INTERVAL)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Unexpected error: {type(e).__name__}: {e}")
                await asyncio.sleep(ERROR_COOLDOWN)

    async def stop(self):
        """Clean shutdown"""
        print("\nStopping bot...")
        self.running = False
        if self.session:
            await self.session.close()
        if self.bot and CHAT_ID:
            await self.send_to_telegram("🛑 Live Price Bot Stopped")

async def main():
    bot = LivePriceBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
    print("Bot shutdown complete")

if __name__ == "__main__":
    print(f"Starting Live Price Bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.run(main())