#!/usr/bin/env python3
"""
TextBee diagnostics for the SeedIQ delayed-OTP investigation.

Reads SEEDIQ_TEXTBEE_API_KEY / TEXTBEE_API_KEY from the environment (use
`railway run` so the production value is injected without ever being printed),
then queries the TextBee gateway API.

Safety properties:
  * never prints the API key
  * never prints message bodies (they contain OTPs) - only their length
  * masks recipient numbers to the last 4 digits
  * read-only: GET requests only

Usage (with `railway run`):
  railway run python3 textbee_diagnostics.py devices
  railway run python3 textbee_diagnostics.py messages --limit 100
  railway run python3 textbee_diagnostics.py pending
  railway run python3 textbee_diagnostics.py batch <smsBatchId>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = (os.environ.get("SEEDIQ_TEXTBEE_BASE_URL") or "https://api.textbee.dev").rstrip("/")
IST = timezone(timedelta(hours=5, minutes=30))
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def api_key() -> str:
    key = (os.environ.get("SEEDIQ_TEXTBEE_API_KEY") or os.environ.get("TEXTBEE_API_KEY") or "").strip()
    if not key:
        print("ERROR: no TextBee API key in the environment (use `railway run`).", file=sys.stderr)
        sys.exit(2)
    return key


def get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    if params:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-api-key", api_key())
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def ts(v) -> str:
    if not v:
        return "-"
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return str(v)
    return dt.astimezone(IST).strftime("%m-%d %H:%M:%S IST")


def minutes(a, b) -> str:
    """(b - a) in minutes; '-' if either is missing."""
    if not a or not b:
        return "-"
    try:
        da = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        db = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
    except ValueError:
        return "?"
    return f"{(db - da).total_seconds() / 60:.1f}m"


def mask_phone(p: str) -> str:
    p = str(p or "")
    digits = "".join(ch for ch in p if ch.isdigit())
    return ("+" + digits[:2] + "*****" + digits[-4:]) if len(digits) >= 6 else "+*****"


def cmd_devices() -> None:
    data = get("/api/v1/gateway/devices").get("data", [])
    now = datetime.now(timezone.utc)
    print(f"devices: {len(data)}  (now {now.astimezone(IST).strftime('%m-%d %H:%M:%S IST')})")
    for d in data:
        lh = d.get("lastHeartbeat")
        age = "-"
        if lh:
            try:
                age = f"{(now - datetime.fromisoformat(str(lh).replace('Z', '+00:00'))).total_seconds() / 60:.0f} min ago"
            except ValueError:
                age = "?"
        print(f"\n- {d.get('name')} [{d.get('_id')}]")
        print(f"  enabled={d.get('enabled')} isDefault={d.get('isDefault')} "
              f"{d.get('brand')} {d.get('model')} os={d.get('osVersion')} app={d.get('appVersionName')}")
        print(f"  heartbeatEnabled={d.get('heartbeatEnabled')} interval={d.get('heartbeatIntervalMinutes')}m "
              f"lastHeartbeat={ts(lh)} ({age})")
        print(f"  sentSMSCount={d.get('sentSMSCount')} smsSendDelaySeconds={d.get('smsSendDelaySeconds')} "
              f"receiveSMSEnabled={d.get('receiveSMSEnabled')}")
        p = d.get("powerInfo") or {}
        b = d.get("batteryInfo") or {}
        n = d.get("networkInfo") or {}
        print(f"  power: ignoringBatteryOptimizations={p.get('isIgnoringBatteryOptimizations')} "
              f"deviceIdle={p.get('isDeviceIdleMode')} powerSave={p.get('isPowerSaveMode')} "
              f"powerUpdated={ts(p.get('lastUpdated'))}")
        print(f"  battery: {b.get('percentage')}% charging={b.get('isCharging')} updated={ts(b.get('lastUpdated'))}")
        print(f"  network: {n.get('networkType')} updated={ts(n.get('lastUpdated'))}")
        sims = (d.get("simInfo") or {}).get("sims") or []
        print(f"  simInfo updated={ts((d.get('simInfo') or {}).get('lastUpdated'))} sims={len(sims)}")


def message_row(m: dict) -> None:
    dev = (m.get("device") or {}).get("_id")
    body = m.get("message") or ""
    print(
        f"\n- {m.get('_id')}  status={m.get('status')}  dir={m.get('direction')}  "
        f"to={mask_phone(m.get('recipient'))}  body_len={len(body)}  device={dev}  batch={m.get('smsBatch')}"
    )
    print(f"  requested={ts(m.get('requestedAt'))}  due={ts(m.get('dispatchDueAt'))}  "
          f"dispatched={ts(m.get('dispatchedAt'))}")
    print(f"  pushReceived={ts(m.get('pushReceivedAt'))}  attempted={ts(m.get('sendAttemptedAt'))}  "
          f"sent={ts(m.get('sentAt'))}  delivered={ts(m.get('deliveredAt'))}")
    print(f"  deltas: req->dispatched {minutes(m.get('requestedAt'), m.get('dispatchedAt'))} | "
          f"dispatched->push {minutes(m.get('dispatchedAt'), m.get('pushReceivedAt'))} | "
          f"push->attempted {minutes(m.get('pushReceivedAt'), m.get('sendAttemptedAt'))} | "
          f"attempted->sent {minutes(m.get('sendAttemptedAt'), m.get('sentAt'))} | "
          f"req->sent {minutes(m.get('requestedAt'), m.get('sentAt'))}")
    if m.get("errorCode") or m.get("errorMessage"):
        print(f"  error: {m.get('errorCode')} {m.get('errorMessage')}")
    print(f"  dispatchAttempts={m.get('dispatchAttempts')} overLimit={m.get('overLimit')} "
          f"created={ts(m.get('createdAt'))}")


def cmd_messages(limit: int, status: str | None) -> None:
    params = {"direction": "sent", "limit": min(limit, 100), "order": "desc"}
    if status:
        params["status"] = status
    resp = get("/api/v1/gateway/messages", params)
    rows = resp.get("data", [])
    meta = resp.get("meta", {})
    print(f"sent messages fetched: {len(rows)}  meta={json.dumps(meta)}")
    for m in rows:
        message_row(m)


def cmd_summary(limit: int) -> None:
    rows = get("/api/v1/gateway/messages", {"direction": "sent", "limit": min(limit, 100), "order": "desc"}).get("data", [])
    print(f"{'status':<10} {'requested (IST)':<18} {'pushRecv (IST)':<18} {'sent (IST)':<18} "
          f"{'req>push':>8} {'req>sent':>8} {'att':>3}  batch/err")
    for m in rows:
        print(
            f"{str(m.get('status')):<10} {ts(m.get('requestedAt')):<18} {ts(m.get('pushReceivedAt')):<18} "
            f"{ts(m.get('sentAt')):<18} {minutes(m.get('requestedAt'), m.get('pushReceivedAt')):>8} "
            f"{minutes(m.get('requestedAt'), m.get('sentAt')):>8} {str(m.get('dispatchAttempts')):>3}  "
            f"{m.get('smsBatch') or '-'}{((' ' + str(m.get('errorCode'))) if m.get('errorCode') else '')}"
        )


def cmd_batch(batch_id: str) -> None:
    devices = get("/api/v1/gateway/devices").get("data", [])
    for d in devices:
        try:
            b = get(f"/api/v1/gateway/devices/{d.get('_id')}/sms-batch/{batch_id}").get("data") or {}
        except Exception:
            continue
        print(f"batch {batch_id} on device {d.get('_id')}: {json.dumps({k: v for k, v in b.items() if k != 'messages'})}")
        for m in b.get("messages", []) or []:
            message_row(m)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices")
    p_msg = sub.add_parser("messages")
    p_msg.add_argument("--limit", type=int, default=50)
    p_msg.add_argument("--status", default=None)
    p_sum = sub.add_parser("summary")
    p_sum.add_argument("--limit", type=int, default=100)
    sub.add_parser("pending")
    p_b = sub.add_parser("batch")
    p_b.add_argument("batch_id")
    a = ap.parse_args()

    if a.cmd == "devices":
        cmd_devices()
    elif a.cmd == "messages":
        cmd_messages(a.limit, a.status)
    elif a.cmd == "pending":
        cmd_messages(100, "pending")
    elif a.cmd == "summary":
        cmd_summary(a.limit)
    elif a.cmd == "batch":
        cmd_batch(a.batch_id)


if __name__ == "__main__":
    main()
