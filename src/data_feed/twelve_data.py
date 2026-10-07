import asyncio
import aiohttp
import pandas as pd
import time
from .base import MarketDataFeed
from ..config import settings

class TwelveDataFeed(MarketDataFeed):
    def __init__(self):
        self.api_key = settings.TWELVE_DATA_API_KEY
        self.base_url = "https://api.twelvedata.com"
        self.last_call_time = 0.0
        self.rate_limit_delay = 8.0  # Ensures max 7.5 requests per minute

    async def _rate_limit(self):
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.last_call_time = time.time()

    async def fetch_candles(self, symbol: str, interval: str = "5min", n_bars: int = 100) -> pd.DataFrame:
        await self._rate_limit()
        url = f"{self.base_url}/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": n_bars,
            "apikey": self.api_key,
            "format": "JSON"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if "values" not in data:
                    raise ValueError(f"API Error or Rate Limit hit: {data}")
                    
                df = pd.DataFrame(data["values"])
                df['datetime'] = pd.to_datetime(df['datetime'])
                
                for col in ['open', 'high', 'low', 'close']:
                    if col in df.columns:
                        df[col] = df[col].astype(float)
                if 'volume' in df.columns:
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0)
                
                # Sort chronologically for pandas_ta compatibility
                df = df.sort_values('datetime').reset_index(drop=True)
                return df

    async def get_latest_price(self, symbol: str) -> float:
        await self._rate_limit()
        url = f"{self.base_url}/price"
        params = {"symbol": symbol, "apikey": self.api_key}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if "price" not in data:
                    raise ValueError(f"Failed to fetch price for {symbol}: {data}")
                return float(data['price'])
