from abc import ABC, abstractmethod
from typing import List, Dict
import pandas as pd

class MarketDataFeed(ABC):
    """Abstract base class for all market data providers."""
    
    @abstractmethod
    async def fetch_candles(self, symbol: str, interval: str, n_bars: int) -> pd.DataFrame:
        """Fetches historical OHLCV candle data for a single symbol."""
        pass

    @abstractmethod
    async def fetch_batch_candles(self, symbols: List[str], interval: str, n_bars: int) -> Dict[str, pd.DataFrame]:
        """Fetches historical OHLCV candle data for multiple symbols in a single batch request."""
        pass

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        """Fetches the latest real-time closing price for the symbol."""
        pass

# Alias for compatibility with BaseDataFeed imports
BaseDataFeed = MarketDataFeed
