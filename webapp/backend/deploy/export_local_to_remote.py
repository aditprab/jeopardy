#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from urllib.parse import urlparse, urlunparse


def redact_db_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.password:
        return url
    netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
    return urlunparse(parsed._replace(netloc=netloc))


def require_binary(name: str):
    if shutil.which(name) is None:
        raise RuntimeError(f"Required binary not found in PATH: {name}")


def run_cmd(cmd: list[str]):
    subprocess.run(cmd, check=True)


def stream_dump_to_target(source_url: str, target_url: str):
    dump_cmd = [
        "pg_dump",
        source_url,
        "--format=plain",
        "--encoding=UTF8",
        "--no-owner",
        "--no-privileges",
    ]
    restore_cmd = ["psql", target_url, "-v", "ON_ERROR_STOP=1"]

    dump_proc = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE)
    if dump_proc.stdout is None:
        raise RuntimeError("Failed to start pg_dump")

    restore_proc = subprocess.Popen(restore_cmd, stdin=dump_proc.stdout)
    dump_proc.stdout.close()
    restore_rc = restore_proc.wait()
    dump_rc = dump_proc.wait()

    if dump_rc != 0:
        raise RuntimeError(f"pg_dump failed with exit code {dump_rc}")
    if restore_rc != 0:
        raise RuntimeError(f"psql restore failed with exit code {restore_rc}")


def main():
    parser = argparse.ArgumentParser(
        description="Clone a local Postgres DB into a remote Postgres DB (e.g., Railway).",
    )
    parser.add_argument(
        "--source-url",
        default="postgresql://jeopardy:jeopardy@localhost:5433/jeopardy",
        help="Source Postgres URL (default: local jeopardy DB).",
    )
    parser.add_argument(
        "--target-url",
        required=True,
        help="Target Postgres URL (Railway URL).",
    )
    parser.add_argument(
        "--drop-target",
        action="store_true",
        help="Drop and recreate target public schema before import.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge destructive operations and proceed.",
    )
    args = parser.parse_args()

    require_binary("pg_dump")
    require_binary("psql")

    if args.source_url == args.target_url:
        raise RuntimeError("Source and target URLs are identical. Refusing to run.")

    print("Source:", redact_db_url(args.source_url))
    print("Target:", redact_db_url(args.target_url))
    if not args.yes:
        print("\nRefusing to run without --yes.")
        print("Re-run with --yes when you're ready.")
        sys.exit(1)

    if args.drop_target:
        print("\nDropping target public schema...")
        run_cmd(
            [
                "psql",
                args.target_url,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
            ]
        )

    print("\nStreaming pg_dump -> psql...")
    stream_dump_to_target(args.source_url, args.target_url)

    print("\nDone. Verifying core table counts on target:")
    run_cmd(
        [
            "psql",
            args.target_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            (
                "SELECT "
                "(SELECT count(*) FROM categories) AS categories, "
                "(SELECT count(*) FROM games) AS games, "
                "(SELECT count(*) FROM clues) AS clues, "
                "(SELECT count(*) FROM game_contestants) AS game_contestants;"
            ),
        ]
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
