"""Run the Mini App FastAPI server with a PostgreSQL database connection.

Usage (PowerShell):
  $env:DATABASE_URL = "postgresql://user:pass@host:5432/db"
  $env:API_PORT = "8080"
  python .\load_tests\run_api_with_db.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.api_server import create_api_app
from app.core.database import create_database


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL env var is required.")

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))

    db = create_database(db_url)
    app = create_api_app(db=db, bot_token=os.getenv("TELEGRAM_BOT_TOKEN"))

    uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)


if __name__ == "__main__":
    main()
