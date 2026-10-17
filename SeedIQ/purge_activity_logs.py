#!/usr/bin/env python3
"""
SeedIQ — activity-log data cleanup.

Permanently removes recorded activity-log rows from BOTH stores (the local
SQLite audit table and the Supabase mirror). The logger itself, the log table
and every future write path are untouched, so activity logging keeps working and
later legitimate actions are still recorded.

This is a DATA operation. It deliberately has no "hide the screen" mode.

Usage
-----
    python purge_activity_logs.py --dry-run                 # show what would go
    python purge_activity_logs.py --yes                     # clear all log rows
    python purge_activity_logs.py --before 2026-09-01 --yes # only older rows
    python purge_activity_logs.py --event-type USER_LOGIN --yes
    python purge_activity_logs.py --user-id 1 --user-id 2 --yes

Nothing else is ever deleted: no users, no roles, no predictions, no datasets.
"""

import argparse
import sqlite3
import sys

import activity_logger


def build_clause(args) -> tuple[str, list]:
    where, params = [], []
    if args.before:
        where.append("created_at < ?")
        params.append(args.before)
    if args.user_id:
        where.append(f"user_id IN ({','.join('?' for _ in args.user_id)})")
        params.extend([str(u) for u in args.user_id])
    if args.event_type:
        where.append(f"event_type IN ({','.join('?' for _ in args.event_type)})")
        params.extend(args.event_type)
    return ((" WHERE " + " AND ".join(where)) if where else ""), params


def preview(args) -> tuple[int, list]:
    clause, params = build_clause(args)
    conn = sqlite3.connect(activity_logger.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    total = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
    matched = conn.execute(f"SELECT COUNT(*) FROM activity_logs{clause}", params).fetchone()[0]
    sample = conn.execute(
        f"SELECT id, user_id, event_type, status, created_at FROM activity_logs{clause}"
        " ORDER BY id DESC LIMIT 8",
        params,
    ).fetchall()
    conn.close()
    print(f"local activity_logs rows: {total}   matching this purge: {matched}")
    for r in sample:
        print(f"  #{r['id']} {r['event_type']:24} user={r['user_id']} {r['created_at']} {r['status']}")
    return matched, [dict(r) for r in sample]


def main() -> int:
    p = argparse.ArgumentParser(description="Purge SeedIQ activity-log records (SQLite + Supabase).")
    p.add_argument("--before", help="only rows created before this 'YYYY-MM-DD HH:MM:SS'")
    p.add_argument("--user-id", action="append", help="only these user ids (repeatable)")
    p.add_argument("--event-type", action="append", help="only these event types (repeatable)")
    p.add_argument("--dry-run", action="store_true", help="report without deleting")
    p.add_argument("--yes", action="store_true", help="confirm the deletion")
    args = p.parse_args()

    print(f"database: {activity_logger.DATABASE_PATH}\n")
    matched, _ = preview(args)

    if args.dry_run:
        print("\nDRY RUN — nothing deleted.")
        return 0
    if not args.yes:
        print("\nRefusing to delete without --yes (or use --dry-run to preview).")
        return 2
    if matched == 0:
        print("\nNothing to delete. The mirror is still checked below.")

    outcome = activity_logger.purge_activity_logs(
        before=args.before, user_ids=args.user_id, event_types=args.event_type
    )
    print("\nresult:")
    for k, v in outcome.items():
        print(f"  {k}: {v}")

    remaining, _ = preview(args)
    print(f"\nlocal rows matching the filter after purge: {remaining}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
