import asyncio
import logging
import pandas as pd
import yfinance as yf
from .base import MarketDataFeed

logger = logging.getLogger(__name__)

class YahooFinanceFeed(MarketDataFeed):
    """Zero-quota, free real-time market data feed powered by Yahoo Finance."""

    def __init__(self):
        pass

    def _normalize_symbol(self, symbol: str) -> str:
        s = symbol.replace("/", "").replace(" ", "").upper()
        return s if "=X" in s else f"{s}=X"

    def _map_interval(self, interval: str) -> str:
        interval_clean = interval.lower().replace("in", "")
        if interval_clean in ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d"]:
            return interval_clean
        if "5" in interval:
            return "5m"
        if "15" in interval:
            return "15m"
        if "1" in interval:
            return "1m"
        return "5m"

    async def fetch_candles(self, symbol: str, interval: str = "5min", n_bars: int = 250) -> pd.DataFrame:
        yf_sym = self._normalize_symbol(symbol)
        yf_int = self._map_interval(interval)

        def _download():
            t = yf.Ticker(yf_sym)
            period = "5d" if yf_int in ["5m", "15m", "30m", "60m", "1h"] else "1d"
            return t.history(period=period, interval=yf_int)

        try:
            df = await asyncio.to_thread(_download)
            if df is None or df.empty:
                logger.warning(f"[YahooFinance] No data returned for {yf_sym}")
                return pd.DataFrame()

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]

            if "datetime" not in df.columns and "date" in df.columns:
                df = df.rename(columns={"date": "datetime"})

            # Ensure timezone-naive datetime
            df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

            # Ensure numeric OHLCV
            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)
            if "volume" in df.columns:
                df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)

            df = df.sort_values("datetime").reset_index(drop=True)
            if len(df) > n_bars:
                df = df.tail(n_bars).reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"[YahooFinance] Failed to fetch candles for {symbol} ({yf_sym}): {e}")
            return pd.DataFrame()

    async def get_latest_price(self, symbol: str) -> float:
        yf_sym = self._normalize_symbol(symbol)

        def _get_price():
            t = yf.Ticker(yf_sym)
            df = t.history(period="1d", interval="1m")
            if df.empty:
                df = t.history(period="1d", interval="5m")
            if df.empty:
                raise ValueError(f"No price data available for {yf_sym}")
            return float(df["Close"].iloc[-1])

        return await asyncio.to_thread(_get_price)
