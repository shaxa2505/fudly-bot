#!/usr/bin/env python3
"""Audit environment variable usage in runtime code.

Finds env keys used in runtime modules and compares them with:
1) `.env.example` (documentation coverage)
2) `.env` (local completeness, optional)

Usage:
  python scripts/audit_env.py
  python scripts/audit_env.py --strict
  python scripts/audit_env.py --env-file .env.prod.export
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    "tests",
}

DEFAULT_SCAN_PATHS = [
    "app",
    "handlers",
    "database_pg_module",
    "bot.py",
    "database.py",
    "database_pg.py",
    "logging_config.py",
    "fsm_storage_pg.py",
]

ENV_PATTERNS = [
    re.compile(r"""os\.getenv\(\s*['"]([A-Z0-9_]+)['"]"""),
    re.compile(r"""os\.environ\[\s*['"]([A-Z0-9_]+)['"]\s*\]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z0-9_]+)['"]"""),
]

ENV_FILE_PATTERN = re.compile(r"^\s*([A-Z][A-Z0-9_]+)\s*=")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit env variable usage vs .env.example and .env."
    )
    parser.add_argument(
        "--scan-path",
        action="append",
        default=[],
        help="Additional path to scan for Python files (relative to repo root).",
    )
    parser.add_argument(
        "--example-file",
        default=".env.example",
        help="Path to env example file (default: .env.example).",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to env file to validate (default: .env, if exists).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if missing keys are detected.",
    )
    return parser.parse_args()


def iter_python_files(root: Path, scan_paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for scan_path in scan_paths:
        target = (root / scan_path).resolve()
        if not target.exists():
            continue
        if target.is_file():
            if target.suffix == ".py":
                files.append(target)
            continue

        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for filename in filenames:
                if filename.endswith(".py"):
                    files.append(Path(dirpath) / filename)
    return sorted(set(files))


def extract_env_keys_from_code(files: list[Path]) -> list[str]:
    keys: set[str] = set()
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
        for pattern in ENV_PATTERNS:
            keys.update(pattern.findall(content))
    return sorted(keys)


def extract_env_keys_from_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.lstrip("\ufeff")
        match = ENV_FILE_PATTERN.match(line)
        if match:
            keys.add(match.group(1))
    return sorted(keys)


def print_list(title: str, values: list[str]) -> None:
    print(title)
    if not values:
        print("  (none)")
        return
    for value in values:
        print(f"  - {value}")


def main() -> int:
    args = parse_args()

    scan_paths = DEFAULT_SCAN_PATHS + args.scan_path
    code_files = iter_python_files(PROJECT_ROOT, scan_paths)
    runtime_keys = extract_env_keys_from_code(code_files)

    example_path = (PROJECT_ROOT / args.example_file).resolve()
    env_example_keys = extract_env_keys_from_file(example_path)
    missing_in_example = sorted(set(runtime_keys) - set(env_example_keys))

    env_file_path = (PROJECT_ROOT / args.env_file).resolve()
    env_file_keys = extract_env_keys_from_file(env_file_path)
    missing_in_env_file = sorted(set(runtime_keys) - set(env_file_keys)) if env_file_keys else []

    print(f"Scanned Python files: {len(code_files)}")
    print(f"Runtime env keys in code: {len(runtime_keys)}")
    print(f"Keys in {args.example_file}: {len(env_example_keys)}")
    if env_file_keys:
        print(f"Keys in {args.env_file}: {len(env_file_keys)}")
    else:
        print(f"{args.env_file} not found or empty; skipping local completeness check.")
    print()

    print_list(f"Missing in {args.example_file}:", missing_in_example)
    print()
    if env_file_keys:
        print_list(f"Missing in {args.env_file}:", missing_in_env_file)
        print()

    if args.strict and (missing_in_example or missing_in_env_file):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
