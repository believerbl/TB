import numpy as np
import pandas as pd

# Forward-compatibility shim: pandas_ta requires np.NaN which was deprecated in numpy >= 2.0
if not hasattr(np, "NaN"):
    np.NaN = np.nan

import pandas_ta as ta

class IndicatorEngine:
    """Applies multi-factor technical indicators for the Confluence Strategy."""
    
    @staticmethod
    def build_indicators(df: pd.DataFrame) -> pd.DataFrame:
        # Create a copy to prevent SettingWithCopyWarning
        df = df.copy()
        
        # 1. Trend Filter: Exponential Moving Averages
        df['ema_50'] = ta.ema(df['close'], length=50)
        df['ema_200'] = ta.ema(df['close'], length=200)
        
        # 2. Momentum: RSI (14)
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        
        # 3. Momentum: Stochastic RSI for crossover detection
        stoch = ta.stochrsi(df['close'], length=14, rsi_length=14, k=3, d=3)
        if stoch is not None and not stoch.empty:
            df['stoch_k'] = stoch.iloc[:, 0]
            df['stoch_d'] = stoch.iloc[:, 1]
            
        # 4. Volatility: Bollinger Bands (20, 2)
        bbands = ta.bbands(df['close'], length=20, std=2)
        if bbands is not None and not bbands.empty:
            df['bb_lower'] = bbands.iloc[:, 0]
            df['bb_mid'] = bbands.iloc[:, 1]
            df['bb_upper'] = bbands.iloc[:, 2]
            
        # 5. Trend/Momentum Confluence: MACD (12, 26, 9)
        macd = ta.macd(df['close'], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            df['macd_line'] = macd.iloc[:, 0]
            df['macd_hist'] = macd.iloc[:, 1]
            df['macd_signal'] = macd.iloc[:, 2]
            
        # 6. Trade Sizing/Exhaustion: Average True Range (14)
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        return df
