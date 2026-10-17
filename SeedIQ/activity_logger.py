"""
SeedIQ Centralized Audit & Activity Logger
Logs security, user, and data pipeline events to Supabase PostgreSQL and local SQLite.
Never records passwords, OTP codes, or credentials.
"""

import os
import json
import sqlite3
import datetime
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

# Flask is only needed to read the ambient request/session when the caller does
# not pass user_id / ip_address. Importing it defensively keeps this module
# usable from plain scripts (e.g. purge_activity_logs.py) instead of failing at
# import time; every use below is already guarded by try/except.
try:
    from flask import request, session
except Exception:  # pragma: no cover - flask is always present in the web app
    request = None
    session = None

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'seediq.db')
_log_executor = ThreadPoolExecutor(max_workers=2)

def _ensure_sqlite_activity_table():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                event_type TEXT NOT NULL,
                details TEXT,
                status TEXT DEFAULT 'SUCCESS',
                ip_address TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ACTIVITY_LOGGER] SQLite table init error: {e}")

_ensure_sqlite_activity_table()

def purge_activity_logs(
    before: Optional[str] = None,
    user_ids: Optional[list] = None,
    event_types: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Permanently DELETE activity-log rows from BOTH stores (SQLite + Supabase).

    This is a data-cleanup operation, not a UI one: the log table itself, the
    logger and every future write path are untouched, so later legitimate
    actions still create entries. Only rows already recorded are removed.

    Filters are all optional and combine with AND:
        before       - delete rows created strictly before this 'YYYY-MM-DD HH:MM:SS'
        user_ids     - restrict to these user_id values
        event_types  - restrict to these event_type values

    With no filters the whole activity_logs history is cleared — which is the
    documented behaviour and is what the admin console asks for after an explicit
    confirmation.
    """
    result: Dict[str, Any] = {
        "sqlite_deleted": 0,
        "supabase_deleted": 0,
        "sqlite_ok": False,
        "supabase_ok": False,
    }

    where: list = []
    params: list = []
    if before:
        where.append("created_at < ?")
        params.append(before)
    if user_ids:
        where.append(f"user_id IN ({','.join('?' for _ in user_ids)})")
        params.extend([str(u) for u in user_ids])
    if event_types:
        where.append(f"event_type IN ({','.join('?' for _ in event_types)})")
        params.extend(event_types)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    # 1. SQLite — the authoritative local audit store.
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cur = conn.execute(f"DELETE FROM activity_logs{clause}", params)
        result["sqlite_deleted"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
        conn.close()
        result["sqlite_ok"] = True
    except Exception as e:
        result["sqlite_error"] = f"{type(e).__name__}: {e}"
        print(f"[ACTIVITY_LOGGER] SQLite purge failed: {e}")

    # 2. Supabase mirror — PostgREST needs an explicit filter, so translate the
    #    same filters into its query syntax.
    try:
        from supabase_client import supabase
        filters: list = []
        if before:
            filters.append(f"created_at=lt.{before.replace(' ', 'T')}")
        if user_ids:
            filters.append(f"user_id=in.({','.join(str(u) for u in user_ids)})")
        if event_types:
            filters.append(f"event_type=in.({','.join(event_types)})")
        # PostgREST rejects an unfiltered DELETE; use a filter that matches every
        # row when no other filter is supplied.
        query = "&".join(filters) if filters else "id=gte.0"
        ok, count = supabase.delete_rows("activity_logs", query)
        result["supabase_ok"] = ok
        result["supabase_deleted"] = count
    except Exception as e:
        result["supabase_error"] = f"{type(e).__name__}: {e}"

    return result


def log_activity(
    event_type: str,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    status: str = "SUCCESS",
    ip_address: Optional[str] = None,
    token: Optional[str] = None
):
    """
    Logs an event to both Supabase and SQLite.
    Redacts any sensitive keys automatically.
    """
    if details is None:
        details = {}
        
    # Redact sensitive parameters
    safe_details = {}
    sensitive_keys = {'password', 'password_hash', 'otp', 'code', 'token', 'secret', 'secret_key'}
    for k, v in details.items():
        if k.lower() in sensitive_keys:
            safe_details[k] = "[REDACTED]"
        else:
            safe_details[k] = v

    # Fallback user ID from session if not explicitly provided
    if user_id is None:
        try:
            user_id = str(session.get('user_id', 'anonymous'))
        except Exception:
            user_id = "system"

    # Fallback IP address
    if ip_address is None:
        try:
            ip_address = request.remote_addr or "127.0.0.1"
        except Exception:
            ip_address = "127.0.0.1"

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    details_json = json.dumps(safe_details)

    # 1. Write to local SQLite (always available and instantaneous)
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute('''
            INSERT INTO activity_logs (user_id, event_type, details, status, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (str(user_id), event_type, details_json, status, ip_address, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ACTIVITY_LOGGER] SQLite write failed: {e}")

    # 2. Asynchronous Dual-write to Supabase (never blocks HTTP request thread)
    def _async_supabase_log():
        try:
            from supabase_client import supabase
            supabase.insert_row("activity_logs", {
                "user_id": user_id if (isinstance(user_id, str) and len(user_id) == 36 and '-' in user_id) else None,
                "event_type": event_type,
                "details": safe_details,
                "status": status,
                "ip_address": ip_address,
                "created_at": now_iso
            }, token=token)
        except Exception:
            pass

    try:
        _log_executor.submit(_async_supabase_log)
    except Exception:
        pass
