import sqlite3
import logging
from typing import Optional, Dict, Any
from ..config import settings

logger = logging.getLogger(__name__)

# ─── Database abstraction ────────────────────────────────────────────────────
# Uses PostgreSQL (psycopg2) when DATABASE_URL is set (Render/cloud).
# Falls back to SQLite automatically for local development and demo mode.

def _get_pg_conn():
    import psycopg2
    return psycopg2.connect(settings.DATABASE_URL)

def _sqlite_conn():
    return sqlite3.connect(settings.DB_PATH)

# ─── Schema initialisation ───────────────────────────────────────────────────

def init_db(db_path: Optional[str] = None) -> None:
    """Creates the trade_signals table if it does not already exist."""
    if settings.USE_POSTGRES:
        logger.info("Using PostgreSQL (Neon.tech) for persistence.")
        conn = _get_pg_conn()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_signals (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                confidence_score INTEGER,
                outcome TEXT DEFAULT 'PENDING'
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
    else:
        logger.info("Using SQLite for local persistence.")
        path = db_path or settings.DB_PATH
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trade_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                confidence_score INTEGER,
                outcome TEXT DEFAULT 'PENDING'
            )
        ''')
        conn.commit()
        conn.close()

# ─── Query helpers ────────────────────────────────────────────────────────────

def log_signal(
    db_path: Optional[str],
    symbol: str,
    signal_type: str,
    entry_price: float,
    confidence_score: int
) -> int:
    """Inserts a new PENDING signal and returns its row ID."""
    if settings.USE_POSTGRES:
        conn = _get_pg_conn()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO trade_signals (symbol, signal_type, entry_price, confidence_score, outcome)
               VALUES (%s, %s, %s, %s, 'PENDING') RETURNING id''',
            (symbol, signal_type, entry_price, confidence_score)
        )
        row_id = cursor.fetchone()[0]
        conn.commit(); cursor.close(); conn.close()
        return row_id
    else:
        conn = sqlite3.connect(db_path or settings.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO trade_signals (symbol, signal_type, entry_price, confidence_score, outcome)
               VALUES (?, ?, ?, ?, 'PENDING')''',
            (symbol, signal_type, entry_price, confidence_score)
        )
        conn.commit()
        row_id = cursor.lastrowid
        conn.close()
        return row_id

def update_outcome(db_path: Optional[str], signal_id: int, exit_price: float, outcome: str) -> None:
    """Updates a trade record with exit price and resolved outcome."""
    if settings.USE_POSTGRES:
        conn = _get_pg_conn()
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE trade_signals SET exit_price = %s, outcome = %s WHERE id = %s',
            (exit_price, outcome, signal_id)
        )
        conn.commit(); cursor.close(); conn.close()
    else:
        conn = sqlite3.connect(db_path or settings.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE trade_signals SET exit_price = ?, outcome = ? WHERE id = ?',
            (exit_price, outcome, signal_id)
        )
        conn.commit(); conn.close()

def get_performance_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns aggregated win/loss/tie metrics."""
    sql = '''
        SELECT
            COUNT(CASE WHEN outcome = 'WIN' THEN 1 END)  AS wins,
            COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) AS losses,
            COUNT(CASE WHEN outcome = 'TIE' THEN 1 END)  AS ties,
            COUNT(CASE WHEN outcome IN ('WIN','LOSS','TIE') THEN 1 END) AS total,
            COUNT(CASE WHEN outcome = 'PENDING' THEN 1 END) AS pending
        FROM trade_signals
    '''
    if settings.USE_POSTGRES:
        conn = _get_pg_conn()
        cursor = conn.cursor()
        cursor.execute(sql)
        row = cursor.fetchone()
        cursor.close(); conn.close()
    else:
        conn = sqlite3.connect(db_path or settings.DB_PATH)
        row = conn.cursor().execute(sql).fetchone()
        conn.close()

    wins, losses, ties, total, pending = [x or 0 for x in row]
    decided = wins + losses
    win_rate = round(wins / decided * 100, 2) if decided > 0 else 0.0
    return {
        "total_signals": total,
        "decided_trades": decided,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "pending": pending,
        "win_rate": win_rate,
    }
