from abc import ABC, abstractmethod
import pandas as pd

class MarketDataFeed(ABC):
    """Abstract base class for all market data providers."""
    
    @abstractmethod
    async def fetch_candles(self, symbol: str, interval: str, n_bars: int) -> pd.DataFrame:
        """Fetches historical OHLCV candle data as a sorted pandas DataFrame."""
        pass

    @abstractmethod
    async def get_latest_price(self, symbol: str) -> float:
        """Fetches the latest real-time closing price for the symbol."""
        pass

# Alias for compatibility with BaseDataFeed imports
BaseDataFeed = MarketDataFeed
