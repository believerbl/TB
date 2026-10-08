import asyncio
import aiohttp
import pandas as pd
import time
import logging
from typing import List, Dict
from .base import MarketDataFeed
from ..config import settings

logger = logging.getLogger(__name__)

class TwelveDataFeed(MarketDataFeed):
    """Production market data feed for Twelve Data API with batch querying."""

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

    def _parse_values_to_df(self, values: list) -> pd.DataFrame:
        df = pd.DataFrame(values)
        df['datetime'] = pd.to_datetime(df['datetime'])
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0)
        df = df.sort_values('datetime').reset_index(drop=True)
        return df

    async def fetch_candles(self, symbol: str, interval: str = "5min", n_bars: int = 250) -> pd.DataFrame:
        """Fetches candles for a single symbol."""
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

                return self._parse_values_to_df(data["values"])

    async def fetch_batch_candles(self, symbols: List[str], interval: str = "5min", n_bars: int = 250) -> Dict[str, pd.DataFrame]:
        """
        Fetches candles for ALL requested symbols in a SINGLE network API request.
        Reduces API round-trips and network latency by 1/N.
        """
        if not symbols:
            return {}

        if len(symbols) == 1:
            df = await self.fetch_candles(symbols[0], interval=interval, n_bars=n_bars)
            return {symbols[0]: df}

        await self._rate_limit()
        symbol_param = ",".join(symbols)
        url = f"{self.base_url}/time_series"
        params = {
            "symbol": symbol_param,
            "interval": interval,
            "outputsize": n_bars,
            "apikey": self.api_key,
            "format": "JSON"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if "code" in data and data.get("code") != 200:
                    raise ValueError(f"API Error or Rate Limit hit: {data}")

                result: Dict[str, pd.DataFrame] = {}
                for sym in symbols:
                    sym_data = data.get(sym)
                    if sym_data and isinstance(sym_data, dict) and "values" in sym_data:
                        result[sym] = self._parse_values_to_df(sym_data["values"])
                    elif "values" in data:
                        result[sym] = self._parse_values_to_df(data["values"])
                    else:
                        logger.warning(f"No candle values returned for {sym}: {sym_data}")
                        result[sym] = pd.DataFrame()

                return result

    async def get_latest_price(self, symbol: str) -> float:
        """Fetches real-time price for a single symbol."""
        await self._rate_limit()
        url = f"{self.base_url}/price"
        params = {"symbol": symbol, "apikey": self.api_key}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if "price" not in data:
                    raise ValueError(f"Failed to fetch price for {symbol}: {data}")
                return float(data['price'])
