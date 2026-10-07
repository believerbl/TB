import sqlite3
from typing import Optional, Dict, Any

def init_db(db_path: str = "signals.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            symbol TEXT NOT NULL,
            signal_type TEXT NOT NULL, -- 'CALL' or 'PUT'
            entry_price REAL NOT NULL, -- P_0
            exit_price REAL,           -- P_1
            confidence_score INTEGER,
            outcome TEXT DEFAULT 'PENDING' -- 'WIN', 'LOSS', 'TIE', or 'PENDING'
        )
    ''')
    conn.commit()
    return conn

def log_signal(
    db_path: str,
    symbol: str,
    signal_type: str,
    entry_price: float,
    confidence_score: int
) -> int:
    """Inserts a new trade signal with PENDING status and returns the row ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trade_signals (symbol, signal_type, entry_price, confidence_score, outcome)
        VALUES (?, ?, ?, ?, 'PENDING')
    ''', (symbol, signal_type, entry_price, confidence_score))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id

def update_outcome(
    db_path: str,
    signal_id: int,
    exit_price: float,
    outcome: str
) -> None:
    """Updates an existing trade signal with the exit price and final outcome."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE trade_signals
        SET exit_price = ?, outcome = ?
        WHERE id = ?
    ''', (exit_price, outcome, signal_id))
    conn.commit()
    conn.close()

def get_performance_stats(db_path: str) -> Dict[str, Any]:
    """Computes total trades, wins, losses, ties, and win rate percentage."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN outcome = 'TIE' THEN 1 ELSE 0 END) as ties,
            SUM(CASE WHEN outcome = 'PENDING' THEN 1 ELSE 0 END) as pending
        FROM trade_signals
    ''')
    row = cursor.fetchone()
    conn.close()

    total, wins, losses, ties, pending = row
    total = total or 0
    wins = wins or 0
    losses = losses or 0
    ties = ties or 0
    pending = pending or 0

    decided = wins + losses + ties
    win_rate = (wins / decided * 100.0) if decided > 0 else 0.0

    return {
        "total_signals": total,
        "decided_trades": decided,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "pending": pending,
        "win_rate": round(win_rate, 2)
    }
