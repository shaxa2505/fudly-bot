"""Run the FastAPI server and the API load test in one process.

Usage (PowerShell):
  $env:DATABASE_URL = "postgresql://user:pass@host:5432/db"
  $env:LOAD_CONCURRENCY = "25"
  $env:LOAD_DURATION = "60"
  $env:LOAD_SKIP_REVERSE = "1"
  python .\load_tests\run_api_load_test.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import uvicorn

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.api_server import create_api_app
from app.core.database import create_database


async def run() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL env var is required.")

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8080"))

    os.environ.setdefault("BASE_URL", f"http://{host}:{port}")
    os.environ.setdefault("LOAD_SKIP_REVERSE", "1")

    db = create_database(db_url)
    app = create_api_app(db=db, bot_token=os.getenv("TELEGRAM_BOT_TOKEN"))

    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(1)

    from load_tests import load_test_api

    try:
        await load_test_api.main()
    finally:
        server.should_exit = True
        await server_task


if __name__ == "__main__":
    asyncio.run(run())
