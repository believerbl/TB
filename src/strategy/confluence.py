import pandas as pd
from typing import Dict, Any
from ..config import settings

class ConfluenceScorer:
    """Evaluates indicator confluence to generate trade signals with confidence scores."""
    
    @staticmethod
    def analyze(row: pd.Series) -> Dict[str, Any]:
        call_score = 0
        put_score = 0
        call_reasons = []
        put_reasons = []
        
        # --- CALL (Buy) Evaluation ---
        # 1. Macro Trend (30 pts)
        if row.get('close') and row.get('ema_200') and row['close'] > row['ema_200']:
            call_score += 30
            call_reasons.append("Price above EMA 200 (Uptrend)")
            
        # 2. Oversold Momentum (30 pts)
        if pd.notna(row.get('rsi_14')) and row['rsi_14'] < 45:
            call_score += 30
            call_reasons.append(f"RSI Oversold ({row['rsi_14']:.1f})")
            
        # 3. Immediate Momentum Shift (20 pts)
        if (
            pd.notna(row.get('stoch_k')) and pd.notna(row.get('stoch_d'))
            and row['stoch_k'] > row['stoch_d'] and row['stoch_k'] < 40
        ):
            call_score += 20
            call_reasons.append("Stochastic bullish crossover")
            
        # 4. Volatility Exhaustion (20 pts)
        if pd.notna(row.get('bb_lower')) and row['low'] <= row['bb_lower']:
            call_score += 20
            call_reasons.append("Price touching/below lower Bollinger Band")

        # --- PUT (Sell) Evaluation ---
        # 1. Macro Trend (30 pts)
        if row.get('close') and row.get('ema_200') and row['close'] < row['ema_200']:
            put_score += 30
            put_reasons.append("Price below EMA 200 (Downtrend)")
            
        # 2. Overbought Momentum (30 pts)
        if pd.notna(row.get('rsi_14')) and row['rsi_14'] > 55:
            put_score += 30
            put_reasons.append(f"RSI Overbought ({row['rsi_14']:.1f})")
            
        # 3. Immediate Momentum Shift (20 pts)
        if (
            pd.notna(row.get('stoch_k')) and pd.notna(row.get('stoch_d'))
            and row['stoch_k'] < row['stoch_d'] and row['stoch_k'] > 60
        ):
            put_score += 20
            put_reasons.append("Stochastic bearish crossover")
            
        # 4. Volatility Exhaustion (20 pts)
        if pd.notna(row.get('bb_upper')) and row['high'] >= row['bb_upper']:
            put_score += 20
            put_reasons.append("Price touching/above upper Bollinger Band")
            
        # --- Signal Resolution ---
        threshold = settings.CONFIDENCE_THRESHOLD
        
        if call_score >= threshold and call_score > put_score:
            return {
                "signal_type": "CALL",
                "confidence": call_score,
                "reasons": call_reasons,
                "price": row['close']
            }
        elif put_score >= threshold and put_score > call_score:
            return {
                "signal_type": "PUT",
                "confidence": put_score,
                "reasons": put_reasons,
                "price": row['close']
            }
            
        return {
            "signal_type": "NEUTRAL",
            "confidence": max(call_score, put_score),
            "reasons": ["Confluence threshold not met"],
            "price": row['close']
        }
