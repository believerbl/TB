import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from ..data_feed.base import MarketDataFeed
from ..database.models import init_db
from ..config import settings

logger = logging.getLogger(__name__)

class TradeOutcomeEvaluator:
    """Logs signals and automatically resolves WIN/LOSS outcomes after expiry."""
    
    def __init__(self, data_feed: MarketDataFeed, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DB_PATH
        self.data_feed = data_feed
        self.expiry_minutes = 5  # Standard binary options expiry
        # Ensure database and tables exist
        init_db(self.db_path)
        
    def log_signal(self, symbol: str, signal_type: str, entry_price: float, confidence: int) -> int:
        """Saves a newly generated signal to the database as PENDING."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO trade_signals (timestamp, symbol, signal_type, entry_price, confidence_score, outcome)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
            ''', (now_str, symbol, signal_type, entry_price, confidence))
            conn.commit()
            return cursor.lastrowid

    async def evaluate_pending_trades(self) -> int:
        """Scans for expired PENDING trades and resolves their outcome. Returns resolved count."""
        resolved_count = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Identify trades older than the expiry window
            expiry_threshold = datetime.now() - timedelta(minutes=self.expiry_minutes)
            
            cursor.execute('''
                SELECT id, symbol, signal_type, entry_price 
                FROM trade_signals 
                WHERE outcome = 'PENDING' AND timestamp <= ?
            ''', (expiry_threshold.strftime('%Y-%m-%d %H:%M:%S'),))
            
            pending_trades = cursor.fetchall()
            
            for trade in pending_trades:
                trade_id, symbol, signal_type, entry_price = trade
                
                try:
                    # Fetch exit price (P1)
                    exit_price = await self.data_feed.get_latest_price(symbol)
                    
                    # Resolve logic
                    if exit_price == entry_price:
                        outcome = 'TIE'
                    elif (signal_type == 'CALL' and exit_price > entry_price) or \
                         (signal_type == 'PUT' and exit_price < entry_price):
                        outcome = 'WIN'
                    else:
                        outcome = 'LOSS'
                        
                    # Commit outcome
                    cursor.execute('''
                        UPDATE trade_signals 
                        SET exit_price = ?, outcome = ? 
                        WHERE id = ?
                    ''', (exit_price, outcome, trade_id))
                    resolved_count += 1
                    logger.info(f"Resolved Trade #{trade_id} ({symbol} {signal_type}): {outcome} (Entry: {entry_price}, Exit: {exit_price})")
                    
                except Exception as e:
                    logger.error(f"Failed to evaluate trade {trade_id}: {e}")
                    
            conn.commit()
        return resolved_count
            
    def get_performance_stats(self) -> Dict[str, Any]:
        """Calculates live win rate for the Telegram bot and dashboard."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN outcome = 'WIN' THEN 1 END) as wins,
                    COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) as losses,
                    COUNT(CASE WHEN outcome = 'TIE' THEN 1 END) as ties,
                    COUNT(CASE WHEN outcome IN ('WIN', 'LOSS', 'TIE') THEN 1 END) as total,
                    COUNT(CASE WHEN outcome = 'PENDING' THEN 1 END) as pending
                FROM trade_signals
            ''')
            result = cursor.fetchone()
            
            wins, losses, ties, total, pending = [x or 0 for x in result]
            decided = wins + losses
            win_rate = (wins / decided * 100) if decided > 0 else 0.0
            
            return {
                "win_rate": round(win_rate, 2),
                "total_resolved": total,
                "wins": wins,
                "losses": losses,
                "ties": ties,
                "active_pending": pending
            }
