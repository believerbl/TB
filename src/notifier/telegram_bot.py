import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from ..config import settings
from .chart_generator import ChartGenerator

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Bi-directional Telegram bot for interactive commands and signal broadcasting."""
    
    def __init__(self, data_feed, tracker):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.data_feed = data_feed
        self.tracker = tracker
        self.app = None
        # Default to configured CHAT_ID if present, or capture dynamically upon /start
        self.chat_id = settings.CHAT_ID if settings.CHAT_ID else None
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.chat_id = update.effective_chat.id
        await update.message.reply_text(
            "🤖 *TB-Project Core Online*\n\n"
            "Commands:\n"
            "• /status - System health & feed mode\n"
            "• /stats - Live win rate & performance metrics\n"
            "• /chart <symbol> - Generate technical chart (e.g. /chart EUR/USD)\n"
            "• /scan - Perform on-demand market scan",
            parse_mode='Markdown'
        )
        
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mode = "DEMO (Replay Mode)" if settings.DEMO_MODE else "LIVE (API)"
        msg = (
            f"🟢 *System Status: Active*\n"
            f"📡 *Data Mode:* {mode}\n"
            f"⏱ *Expiry Engine:* Running (5-min window)\n"
            f"🎯 *Confidence Threshold:* {settings.CONFIDENCE_THRESHOLD}%\n"
            f"📊 *Watchlist:* {', '.join(settings.TRADING_PAIRS)}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats = self.tracker.get_performance_stats()
        msg = (
            f"📈 *Live Performance Metrics*\n\n"
            f"🎯 *Win Rate:* `{stats['win_rate']}%`\n"
            f"📊 *Total Resolved:* `{stats['total_resolved']}`\n"
            f"✅ *Wins:* `{stats['wins']}` | ❌ *Losses:* `{stats['losses']}`\n"
            f"🤝 *Ties:* `{stats['ties']}`\n"
            f"⏳ *Pending Trades:* `{stats['active_pending']}`"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    async def chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Syntax error. Use: /chart EUR/USD")
            return
            
        symbol = context.args[0].upper()
        await update.message.reply_text(f"⚙️ Generating algorithmic overlay for {symbol}...")
        
        try:
            # Fetch raw data and build indicators on demand
            df = await self.data_feed.fetch_candles(symbol, interval=settings.TIMEFRAME, n_bars=100)
            from ..strategy.indicators import IndicatorEngine
            enriched_df = IndicatorEngine.build_indicators(df)
            
            # Generate and dispatch the image buffer
            image_buf = ChartGenerator.generate_chart(enriched_df, symbol)
            await update.message.reply_photo(photo=image_buf, caption=f"📊 {symbol} 5-min Confluence Analysis")
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            await update.message.reply_text(f"Error generating chart: Ensure {symbol} is a valid ticker.")

    async def broadcast_signal(self, signal_data: dict, symbol: str):
        """Dispatches algorithmic trade setups to the active chat."""
        if not self.chat_id or not self.app:
            return 
            
        reasons = "\n".join([f"• {r}" for r in signal_data['reasons']])
        emoji = "🟢" if signal_data['signal_type'] == 'CALL' else "🔴"
        
        msg = (
            f"{emoji} *NEW {signal_data['signal_type']} SIGNAL ALERT* {emoji}\n\n"
            f"🔹 *Asset:* `{symbol}`\n"
            f"🔹 *Entry Price:* `{signal_data['price']}`\n"
            f"🔹 *Confidence:* `{signal_data['confidence']}%`\n\n"
            f"📋 *Algorithmic Confluence:*\n{reasons}\n\n"
            f"⏳ *Auto-evaluating outcome after 5-min expiry...*"
        )
        try:
            await self.app.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def build(self):
        if not self.token:
            logger.warning("No Telegram token provided. Bot UI disabled.")
            return None
            
        self.app = ApplicationBuilder().token(self.token).build()
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("stats", self.stats))
        self.app.add_handler(CommandHandler("chart", self.chart))
        return self.app
