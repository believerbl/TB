import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# Automatically load from .env, with fallback to ini.env if present
load_dotenv(".env")
load_dotenv("ini.env")

@dataclass
class Config:
    TWELVE_DATA_API_KEY: str = os.getenv("TWELVE_DATA_API_KEY", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    CHAT_ID: str = os.getenv("CHAT_ID", "")
    DB_PATH: str = os.getenv("DB_PATH", "signals.db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")   # Neon.tech PostgreSQL URL
    CONFIDENCE_THRESHOLD: int = int(os.getenv("CONFIDENCE_THRESHOLD", 50))
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "False").lower() in ("true", "1", "yes")
    TRADING_PAIRS: List[str] = field(default_factory=lambda: [
        p.strip() for p in os.getenv("TRADING_PAIRS", "EUR/USD,EUR/JPY,GBP/USD").split(",") if p.strip()
    ])
    TIMEFRAME: str = os.getenv("TIMEFRAME", "5min")
    HISTORY_LENGTH: int = int(os.getenv("HISTORY_LENGTH", 100))
    UPDATE_INTERVAL: int = int(os.getenv("UPDATE_INTERVAL", 120))

    @property
    def USE_POSTGRES(self) -> bool:
        """True when a DATABASE_URL is set (cloud/Render), False falls back to SQLite (local)."""
        return bool(self.DATABASE_URL)

settings = Config()
