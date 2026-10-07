import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..data_feed.base import MarketDataFeed
from ..database.models import init_db
from ..config import settings

logger = logging.getLogger(__name__)

# ─── Placeholder ─────────────────────────────────────────────────────────────
_PG_PLACEHOLDER = "%s"
_SQ_PLACEHOLDER = "?"

def _ph(use_pg: bool) -> str:
    return _PG_PLACEHOLDER if use_pg else _SQ_PLACEHOLDER

def _get_conn(db_path: Optional[str], use_pg: bool):
    if use_pg:
        import psycopg2
        return psycopg2.connect(settings.DATABASE_URL)
    else:
        return sqlite3.connect(db_path or settings.DB_PATH)

# ─── Evaluator ───────────────────────────────────────────────────────────────

class TradeOutcomeEvaluator:
    """Logs signals and automatically resolves WIN/LOSS outcomes after expiry."""

    def __init__(self, data_feed: MarketDataFeed, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DB_PATH
        self.data_feed = data_feed
        self.expiry_minutes = 5
        self.use_pg = settings.USE_POSTGRES
        init_db(self.db_path)
        logger.info(f"TradeOutcomeEvaluator: using {'PostgreSQL' if self.use_pg else 'SQLite'}")

    def log_signal(self, symbol: str, signal_type: str, entry_price: float, confidence: int) -> int:
        """Saves a new signal as PENDING and returns its row ID."""
        ph = _ph(self.use_pg)
        conn = _get_conn(self.db_path, self.use_pg)
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if self.use_pg:
            cursor.execute(
                f'''INSERT INTO trade_signals (timestamp, symbol, signal_type, entry_price, confidence_score, outcome)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 'PENDING') RETURNING id''',
                (now_str, symbol, signal_type, entry_price, confidence)
            )
            row_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                f'''INSERT INTO trade_signals (timestamp, symbol, signal_type, entry_price, confidence_score, outcome)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 'PENDING')''',
                (now_str, symbol, signal_type, entry_price, confidence)
            )
            row_id = cursor.lastrowid
        conn.commit(); cursor.close(); conn.close()
        return row_id

    async def evaluate_pending_trades(self) -> int:
        """Resolves expired PENDING trades. Returns number of trades resolved."""
        resolved_count = 0
        ph = _ph(self.use_pg)
        expiry_threshold = datetime.now() - timedelta(minutes=self.expiry_minutes)
        conn = _get_conn(self.db_path, self.use_pg)
        cursor = conn.cursor()

        cursor.execute(
            f'''SELECT id, symbol, signal_type, entry_price FROM trade_signals
                WHERE outcome = 'PENDING' AND timestamp <= {ph}''',
            (expiry_threshold.strftime('%Y-%m-%d %H:%M:%S'),)
        )
        pending = cursor.fetchall()

        for trade_id, symbol, signal_type, entry_price in pending:
            try:
                exit_price = await self.data_feed.get_latest_price(symbol)
                if exit_price == entry_price:
                    outcome = 'TIE'
                elif (signal_type == 'CALL' and exit_price > entry_price) or \
                     (signal_type == 'PUT' and exit_price < entry_price):
                    outcome = 'WIN'
                else:
                    outcome = 'LOSS'

                cursor.execute(
                    f'UPDATE trade_signals SET exit_price = {ph}, outcome = {ph} WHERE id = {ph}',
                    (exit_price, outcome, trade_id)
                )
                resolved_count += 1
                logger.info(f"Resolved #{trade_id} ({symbol} {signal_type}): {outcome} (Entry:{entry_price} Exit:{exit_price})")
            except Exception as e:
                logger.error(f"Failed to evaluate trade #{trade_id}: {e}")

        conn.commit(); cursor.close(); conn.close()
        return resolved_count

    def get_performance_stats(self) -> Dict[str, Any]:
        """Returns live win/loss metrics from the active database."""
        sql = '''
            SELECT
                COUNT(CASE WHEN outcome = 'WIN' THEN 1 END)  AS wins,
                COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) AS losses,
                COUNT(CASE WHEN outcome = 'TIE' THEN 1 END)  AS ties,
                COUNT(CASE WHEN outcome IN ('WIN','LOSS','TIE') THEN 1 END) AS total,
                COUNT(CASE WHEN outcome = 'PENDING' THEN 1 END) AS pending
            FROM trade_signals
        '''
        conn = _get_conn(self.db_path, self.use_pg)
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        cursor.close(); conn.close()

        wins, losses, ties, total, pending = [x or 0 for x in row]
        decided = wins + losses
        win_rate = round(wins / decided * 100, 2) if decided > 0 else 0.0
        return {
            "win_rate": win_rate,
            "total_resolved": total,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "active_pending": pending,
        }
