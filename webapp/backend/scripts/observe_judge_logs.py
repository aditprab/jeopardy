#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os

import psycopg2


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        dbname=os.getenv("DB_NAME", "jeopardy"),
        user=os.getenv("DB_USER", "jeopardy"),
        password=os.getenv("DB_PASSWORD", "jeopardy"),
    )


def print_rows(title: str, columns: list[str], rows: list[tuple]):
    print(f"== {title} ==")
    if not rows:
        print("(no rows)\n")
        return

    widths = [len(col) for col in columns]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len("" if val is None else str(val)))

    header = " | ".join(columns[i].ljust(widths[i]) for i in range(len(columns)))
    sep = "-+-".join("-" * widths[i] for i in range(len(columns)))
    print(header)
    print(sep)
    for row in rows:
        print(" | ".join(("" if val is None else str(val)).ljust(widths[i]) for i, val in enumerate(row)))
    print()


def main():
    parser = argparse.ArgumentParser(description="Observe recent answer-appeal judge logs.")
    parser.add_argument("--limit", type=int, default=10, help="Rows per section (default: 10)")
    args = parser.parse_args()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  ar.id AS run_id,
                  ar.trace_id,
                  ar.run_type,
                  ar.agent_name,
                  ar.agent_version,
                  ar.policy_version,
                  ar.status,
                  ar.model,
                  ar.prompt_version,
                  ar.latency_ms,
                  ar.prompt_tokens,
                  ar.completion_tokens,
                  ar.total_tokens,
                  ar.guardrail_flags::text,
                  ar.error_message,
                  ar.input_payload::text,
                  ar.output_payload::text,
                  aa.id AS appeal_id,
                  aa.status AS appeal_status,
                  aa.user_justification,
                  aa.overturn,
                  aa.final_correct,
                  aa.reason_code,
                  aa.reason_text,
                  aa.confidence,
                  aa.created_at AS appeal_created_at,
                  aa.decided_at AS appeal_decided_at,
                  ar.started_at,
                  ar.finished_at
                FROM agent_runs ar
                LEFT JOIN answer_appeals aa ON aa.agent_run_id = ar.id
                WHERE ar.run_type = 'answer_appeal'
                ORDER BY ar.id DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            runs = cur.fetchall()
            print_rows(
                f"Recent Judge Runs (limit {args.limit})",
                [
                    "run_id",
                    "trace_id",
                    "run_type",
                    "agent_name",
                    "agent_version",
                    "policy_version",
                    "status",
                    "model",
                    "prompt_version",
                    "latency_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "guardrail_flags",
                    "error_message",
                    "input_payload",
                    "output_payload",
                    "appeal_id",
                    "appeal_status",
                    "user_justification",
                    "overturn",
                    "final_correct",
                    "reason_code",
                    "reason_text",
                    "confidence",
                    "appeal_created_at",
                    "appeal_decided_at",
                    "started_at",
                    "finished_at",
                ],
                runs,
            )

            cur.execute(
                """
                SELECT
                  e.agent_run_id AS run_id,
                  e.event_type,
                  e.level,
                  e.message,
                  e.payload::text,
                  e.created_at
                FROM agent_run_events e
                JOIN agent_runs ar ON ar.id = e.agent_run_id
                WHERE ar.run_type = 'answer_appeal'
                ORDER BY e.id DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            events = cur.fetchall()
            print_rows(
                f"Recent Judge Events (limit {args.limit})",
                ["run_id", "event_type", "level", "message", "payload", "created_at"],
                events,
            )

            cur.execute(
                """
                SELECT
                  art.agent_run_id AS run_id,
                  art.artifact_type,
                  art.content::text,
                  art.created_at
                FROM agent_run_artifacts art
                JOIN agent_runs ar ON ar.id = art.agent_run_id
                WHERE ar.run_type = 'answer_appeal'
                ORDER BY art.id DESC
                LIMIT %s
                """,
                (args.limit,),
            )
            decisions = cur.fetchall()
            print_rows(
                f"Recent Judge Artifacts (limit {args.limit})",
                ["run_id", "artifact_type", "content", "created_at"],
                decisions,
            )

    print("Tip: run with '--limit 5' while testing appeals.")


if __name__ == "__main__":
    main()
