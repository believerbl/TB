#!/bin/bash
set -e

echo "=== TB-Project: Starting Deployment ==="

# Start the trading engine in the background (live market mode)
echo "[1/2] Starting trading bot..."
python run_bot.py --live &

# Start the FastAPI dashboard in the foreground on Render's dynamic PORT
echo "[2/2] Starting FastAPI dashboard on port $PORT..."
uvicorn dashboard:app --host 0.0.0.0 --port "${PORT:-8000}"
