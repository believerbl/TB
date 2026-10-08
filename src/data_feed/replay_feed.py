import pandas as pd
import asyncio
from .base import MarketDataFeed

class ReplayFeed(MarketDataFeed):
    def __init__(self, csv_path: str):
        self.df = pd.read_csv(csv_path)
        self.df['datetime'] = pd.to_datetime(self.df['datetime'])
        # Sort chronologically to ensure proper replay
        self.df = self.df.sort_values('datetime').reset_index(drop=True)
        # Ensure standard float columns
        for col in ['open', 'high', 'low', 'close']:
            if col in self.df.columns:
                self.df[col] = self.df[col].astype(float)
        if 'volume' in self.df.columns:
            self.df['volume'] = pd.to_numeric(self.df['volume'], errors='coerce').fillna(0.0)

        self.current_index = min(100, len(self.df) - 1)  # Start with enough history for indicator warm-up
        self.max_index = len(self.df) - 1

    async def fetch_candles(self, symbol: str, interval: str = "5min", n_bars: int = 100) -> pd.DataFrame:
        await asyncio.sleep(0.3)  # Simulate network latency for a realistic demo
        
        start_idx = max(0, self.current_index - n_bars)
        chunk = self.df.iloc[start_idx:self.current_index].copy()
        
        # Step forward in time for the next call
        if self.current_index < self.max_index:
            self.current_index += 1
            
        return chunk

    async def fetch_batch_candles(self, symbols: list, interval: str = "5min", n_bars: int = 100) -> dict:
        chunk = await self.fetch_candles(symbols[0] if symbols else "EUR/USD", interval=interval, n_bars=n_bars)
        return {sym: chunk for sym in symbols}

    async def get_latest_price(self, symbol: str) -> float:
        return float(self.df.iloc[self.current_index]['close'])
