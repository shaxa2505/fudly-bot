#!/usr/bin/env python3
"""Audit Railway environment variables against runtime env keys.

Requires Railway CLI and a linked project (`railway link`).

Usage:
  python scripts/audit_railway_env.py
  python scripts/audit_railway_env.py --service bot --environment production --strict
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from audit_env import (  # type: ignore[import]
    DEFAULT_SCAN_PATHS,
    extract_env_keys_from_code,
    iter_python_files,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Railway variables with env keys used in runtime code."
    )
    parser.add_argument("--service", default="", help="Railway service name (optional).")
    parser.add_argument("--environment", default="", help="Railway environment name (optional).")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if missing vars are detected.",
    )
    return parser.parse_args()


def load_railway_vars(service: str, environment: str) -> dict[str, str]:
    railway_bin = shutil.which("railway") or shutil.which("railway.exe")
    if not railway_bin:
        raise RuntimeError("Railway CLI is not installed or not in PATH.")

    cmd = [railway_bin, "variables", "--json"]
    if service:
        cmd += ["--service", service]
    if environment:
        cmd += ["--environment", environment]

    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "railway variables failed")

    data = json.loads(proc.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Railway variables response format.")
    normalized: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        normalized[key] = "" if value is None else str(value)
    return normalized


def main() -> int:
    args = parse_args()

    code_files = iter_python_files(PROJECT_ROOT, DEFAULT_SCAN_PATHS)
    runtime_keys = extract_env_keys_from_code(code_files)

    try:
        railway_vars = load_railway_vars(args.service, args.environment)
    except Exception as exc:
        print(f"Failed to load Railway variables: {exc}")
        print("Tip: run `railway link` in this repository first.")
        return 2

    railway_keys = set(railway_vars.keys())
    missing = sorted(set(runtime_keys) - railway_keys)

    print(f"Runtime env keys in code: {len(runtime_keys)}")
    print(f"Railway env keys: {len(railway_keys)}")
    print()
    print("Missing in Railway:")
    if not missing:
        print("  (none)")
    else:
        for key in missing:
            print(f"  - {key}")

    if args.strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
