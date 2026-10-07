import sqlite3
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import uvicorn
from src.config import settings
from src.database.models import init_db

app = FastAPI(title="TB-Project Live Dashboard")
templates = Jinja2Templates(directory="templates")

# Ensure DB is initialized
init_db(settings.DB_PATH)

def get_db_stats():
    try:
        with sqlite3.connect(settings.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Aggregate metrics
            cursor.execute('''
                SELECT 
                    COUNT(CASE WHEN outcome = 'WIN' THEN 1 END) as wins,
                    COUNT(CASE WHEN outcome = 'LOSS' THEN 1 END) as losses,
                    COUNT(CASE WHEN outcome = 'TIE' THEN 1 END) as ties,
                    COUNT(CASE WHEN outcome = 'PENDING' THEN 1 END) as pending
                FROM trade_signals
            ''')
            row = cursor.fetchone()
            stats = dict(row) if row else {"wins": 0, "losses": 0, "ties": 0, "pending": 0}
            
            # Recent signals for the data table
            cursor.execute('''
                SELECT timestamp, symbol, signal_type, entry_price, exit_price, confidence_score, outcome 
                FROM trade_signals 
                ORDER BY id DESC LIMIT 10
            ''')
            recent = [dict(r) for r in cursor.fetchall()]
            
            wins, losses = stats.get('wins') or 0, stats.get('losses') or 0
            win_rate = round((wins / (wins + losses) * 100), 2) if (wins + losses) > 0 else 0
            
            return {"stats": stats, "recent": recent, "win_rate": win_rate}
    except Exception as e:
        return {"stats": {"wins": 0, "losses": 0, "ties": 0, "pending": 0}, "recent": [], "win_rate": 0, "error": str(e)}

@app.get("/")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/api/data")
async def api_data():
    """Endpoint for asynchronous frontend polling."""
    return get_db_stats()

if __name__ == "__main__":
    # Run via: python dashboard.py
    uvicorn.run("dashboard:app", host="127.0.0.1", port=8000, reload=True)
