#!/usr/bin/env python3
"""Pre-start checks for deployment safety.

This script is intended to run before the app process in production:
1) Validate critical environment variables.
2) Apply Alembic migrations (optional, enabled by default).
3) Start the target command (if provided).

Usage examples:
  python prestart.py -- python bot.py
  python prestart.py --skip-migrations -- python app/api/api_server.py
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
TRUTHY = {"1", "true", "yes", "y", "on"}


def _env_value(name: str) -> str:
    return os.getenv(name, "").strip()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUTHY


def _is_strict_env() -> bool:
    env = _env_value("ENVIRONMENT").lower()
    railway_env = _env_value("RAILWAY_ENVIRONMENT").lower()
    use_webhook = _env_flag("USE_WEBHOOK", default=False)
    return env == "production" or railway_env == "production" or use_webhook


def _add_if_missing(container: list[str], keys: Iterable[str]) -> None:
    for key in keys:
        if not _env_value(key):
            container.append(key)


def validate_environment() -> tuple[list[str], list[str]]:
    """Return (missing, warnings)."""
    missing: list[str] = []
    warnings: list[str] = []

    # Core runtime requirements
    _add_if_missing(missing, ["TELEGRAM_BOT_TOKEN", "DATABASE_URL"])

    if _is_strict_env():
        _add_if_missing(missing, ["ADMIN_ID"])

    use_webhook = _env_flag("USE_WEBHOOK", default=False)
    if use_webhook:
        _add_if_missing(missing, ["WEBHOOK_URL", "SECRET_TOKEN"])

    # Feature-gated checks
    if _env_flag("ONEC_AUTO_SYNC", default=False):
        _add_if_missing(missing, ["ONEC_BASE_URL", "ONEC_USERNAME", "ONEC_PASSWORD"])

    if _env_flag("UZUM_MERCHANT_REQUIRE_SIGNATURE", default=False):
        _add_if_missing(missing, ["UZUM_MERCHANT_WEBHOOK_SECRET"])

    click_keys = ["CLICK_MERCHANT_ID", "CLICK_SERVICE_ID", "CLICK_SECRET_KEY"]
    click_present = [_env_value(key) for key in click_keys]
    if any(click_present) and not all(click_present):
        _add_if_missing(missing, click_keys)

    payme_keys = ["PAYME_MERCHANT_ID", "PAYME_SECRET_KEY"]
    payme_present = [_env_value(key) for key in payme_keys]
    if any(payme_present) and not all(payme_present):
        _add_if_missing(missing, payme_keys)

    if _env_flag("RUN_DB_MIGRATIONS", default=False) and _is_strict_env():
        warnings.append(
            "RUN_DB_MIGRATIONS=1 enables runtime schema changes. "
            "Prefer Alembic migrations in production."
        )

    if _env_flag("SKIP_DB_INIT", default=False):
        warnings.append("SKIP_DB_INIT=1 is enabled (runtime DB init path is disabled).")

    # De-duplicate while preserving deterministic order.
    missing = sorted(set(missing))
    warnings = sorted(set(warnings))
    return missing, warnings


def apply_migrations(timeout_seconds: int) -> None:
    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    print("[prestart] Applying Alembic migrations: " + " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=False,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic upgrade failed with exit code {result.returncode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run env checks and migrations before app start.")
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip environment validation.",
    )
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Skip Alembic upgrade step.",
    )
    parser.add_argument(
        "--migrations-timeout",
        type=int,
        default=int(os.getenv("MIGRATION_COMMAND_TIMEOUT_SECONDS", "300")),
        help="Alembic command timeout in seconds (default: 300 or MIGRATION_COMMAND_TIMEOUT_SECONDS).",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to start after checks. Use '--' before the command.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    run_env_validation = _env_flag("RUN_ENV_VALIDATION_ON_START", default=True)
    if not args.skip_env_check and run_env_validation:
        missing, warnings = validate_environment()
        for warning in warnings:
            print(f"[prestart] Warning: {warning}")
        if missing:
            print("[prestart] Missing required environment variables:")
            for key in missing:
                print(f"  - {key}")
            return 2
        print("[prestart] Environment validation passed.")

    run_migrations = _env_flag("RUN_MIGRATIONS_ON_START", default=True)
    if not args.skip_migrations and run_migrations:
        if not _env_value("DATABASE_URL"):
            print("[prestart] Skipping migrations: DATABASE_URL is empty.")
        else:
            try:
                apply_migrations(timeout_seconds=args.migrations_timeout)
            except Exception as exc:
                print(f"[prestart] Migration step failed: {exc}")
                return 3
    else:
        print("[prestart] Migration step skipped.")

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]

    if command:
        print("[prestart] Starting command: " + " ".join(command))
        proc = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        return proc.returncode

    print("[prestart] No command provided. Checks finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
