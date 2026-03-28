#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Precompute a daily challenge and any missing hint-context classifications. "
            "Defaults to tomorrow in America/New_York so it can be scheduled before midnight ET."
        )
    )
    parser.add_argument(
        "--date",
        default="tomorrow",
        help="Target date: today, tomorrow, or YYYY-MM-DD. Default: tomorrow",
    )
    args = parser.parse_args()

    _load_env_file(BACKEND_DIR / ".env")
    try:
        from daily import ensure_daily_schema, precompute_daily_challenge, resolve_challenge_date
        from db import close_pool, init_pool
        from grading import ensure_grading_schema
    except ImportError as exc:
        raise SystemExit(
            "Missing backend dependencies. Install them with:\n"
            "  pip install -r webapp/backend/requirements.txt"
        ) from exc

    target_date = resolve_challenge_date(args.date)

    init_pool()
    try:
        ensure_grading_schema()
        ensure_daily_schema()
        result = precompute_daily_challenge(target_date)
    finally:
        close_pool()

    print(f"Precomputed challenge for {result['challenge_date']}")
    print(f"Already existed: {result['already_existed']}")
    print(
        "Single: "
        f"{result['single_category_name']} ({', '.join(str(cid) for cid in result['single_clue_ids'])})"
    )
    print(
        "Double: "
        f"{result['double_category_name']} ({', '.join(str(cid) for cid in result['double_clue_ids'])})"
    )
    print(f"Final: {result['final_category_name']} ({result['final_clue_id']})")


if __name__ == "__main__":
    main()
