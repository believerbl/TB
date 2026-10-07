import io
import pandas as pd
import mplfinance as mpf

class ChartGenerator:
    """Generates candlestick charts with technical indicator overlays."""
    
    @staticmethod
    def generate_chart(df: pd.DataFrame, symbol: str) -> io.BytesIO:
        # Prevent mutating the original dataframe
        plot_df = df.copy()
        if 'datetime' in plot_df.columns:
            plot_df['datetime'] = pd.to_datetime(plot_df['datetime'])
            plot_df.set_index('datetime', inplace=True)
        
        # Isolate the most recent 50 candles for a clean visual
        plot_df = plot_df.tail(50)
        
        # Define algorithmic overlays if columns exist
        apds = []
        if 'ema_50' in plot_df.columns and plot_df['ema_50'].notna().any():
            apds.append(mpf.make_addplot(plot_df['ema_50'], color='blue', width=1.5))
        if 'ema_200' in plot_df.columns and plot_df['ema_200'].notna().any():
            apds.append(mpf.make_addplot(plot_df['ema_200'], color='orange', width=2))
        if 'bb_upper' in plot_df.columns and plot_df['bb_upper'].notna().any():
            apds.append(mpf.make_addplot(plot_df['bb_upper'], color='gray', linestyle='dashed', alpha=0.5))
        if 'bb_lower' in plot_df.columns and plot_df['bb_lower'].notna().any():
            apds.append(mpf.make_addplot(plot_df['bb_lower'], color='gray', linestyle='dashed', alpha=0.5))
        
        # Render the chart into a byte buffer for Telegram API compatibility
        buf = io.BytesIO()
        mpf.plot(
            plot_df, 
            type='candle', 
            style='charles', 
            addplot=apds if apds else None, 
            title=f"{symbol} - Live Confluence Engine",
            volume=False, 
            figsize=(10, 6),
            savefig=dict(fname=buf, dpi=100, bbox_inches='tight')
        )
        buf.seek(0)
        return buf
