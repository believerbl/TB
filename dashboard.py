import sqlite3
import logging
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import uvicorn
from src.config import settings
from src.database.models import init_db

app = FastAPI(title="TB-Project Live Dashboard")
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)

# Ensure DB is initialised on startup
init_db(settings.DB_PATH)

def get_db_stats():
    try:
        if settings.USE_POSTGRES:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(settings.DATABASE_URL)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        else:
            conn = sqlite3.connect(settings.DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

        # Aggregate metrics
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN outcome = 'WIN' THEN 1 END)  AS wins,
                COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) AS losses,
                COUNT(CASE WHEN outcome = 'TIE' THEN 1 END)  AS ties,
                COUNT(CASE WHEN outcome = 'PENDING' THEN 1 END) AS pending
            FROM trade_signals
        ''')
        stats = dict(cursor.fetchone())

        # Recent signals
        cursor.execute('''
            SELECT timestamp, symbol, signal_type, entry_price, exit_price, confidence_score, outcome
            FROM trade_signals
            ORDER BY id DESC LIMIT 10
        ''')
        recent = [dict(row) for row in cursor.fetchall()]

        cursor.close()
        conn.close()

        wins  = stats.get('wins') or 0
        losses = stats.get('losses') or 0
        win_rate = round(wins / (wins + losses) * 100, 2) if (wins + losses) > 0 else 0

        return {"stats": stats, "recent": recent, "win_rate": win_rate}

    except Exception as e:
        logger.error(f"DB Error in get_db_stats: {e}")
        return {
            "stats": {"wins": 0, "losses": 0, "ties": 0, "pending": 0},
            "recent": [], "win_rate": 0
        }

@app.get("/")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/data")
async def api_data():
    """Asynchronous JSON endpoint polled by the frontend every 5 seconds."""
    return get_db_stats()

if __name__ == "__main__":
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8000, reload=True)
