#!/usr/bin/env python3
"""Gateway preflight guard — isolated test (no network, no SMS, no production DB).

Policy under test (corrected 2026-10-16):

  * `phone_request_otp` refuses to queue an OTP only on CONCRETE evidence that
    the gateway phone cannot take the message - no enabled device, a disabled
    device, or a recent message TextBee dispatched that the phone never
    acknowledged (`gateway_not_receiving`).
  * A stale heartbeat alone is a health signal, not a send gate: TextBee
    documents that the API still accepts sends for such a device and the
    message waits until the phone comes back
    (https://textbee.dev/docs/troubleshooting/messages-not-sending). Gating
    sign-in on it took the client's logins down on 10-15/10-16.
  * The health check still fails OPEN when it cannot run, a refused attempt
    never burns the cooldown, and no response ever claims carrier delivery.

All HTTP is stubbed via `phone_auth._http_get_json`; all SMS via
`phone_auth.send_sms`. Exit status is the source of truth (0 = all pass).
"""
import datetime
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "SeedIQ"))

from flask import Flask

import phone_auth

SECRET = "test-secret-not-production"
TEST_PHONE = "9110252930"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def iso(minutes_ago: float) -> str:
    t = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes_ago)
    return t.isoformat().replace("+00:00", "Z")


def device(dev_id="dev-1", **over):
    d = {
        "_id": dev_id,
        "enabled": True,
        "isDefault": True,
        "heartbeatEnabled": True,
        "heartbeatIntervalMinutes": 30,
        "lastHeartbeat": iso(5),
        "powerInfo": {"isIgnoringBatteryOptimizations": False, "isDeviceIdleMode": False},
    }
    d.update(over)
    return d


def msg(minutes_ago=5, ack=False):
    t = iso(minutes_ago)
    return {"_id": "m1", "recipient": "+919110252930", "requestedAt": t,
            "pushReceivedAt": t if ack else None, "sentAt": t if ack else None}


def build(tmp_db):
    app = Flask(__name__)
    app.secret_key = SECRET

    def get_db():
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        return conn

    with get_db() as conn:
        conn.execute("""CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, password TEXT, email TEXT UNIQUE,
            display_name TEXT, role TEXT DEFAULT 'Farmer', provider TEXT)""")
        # Create the phone_otp schema up front, mirroring a live database, so a
        # refused request cannot leave the table missing and confuse the checks.
        phone_auth.ensure_phone_schema(conn)
        conn.commit()

    phone_auth.register_phone_auth(
        app, get_db, lambda *a, **k: None, lambda p: "scrypt$stub$not-real",
        SECRET, test_mode=False,
    )
    return app, get_db


def fake_http(scenario):
    def _fake(url, params=None, timeout=6):
        if scenario.get("raise"):
            raise RuntimeError("stub network failure")
        if url.endswith("/devices"):
            return {"data": scenario.get("devices", [])}
        if url.endswith("/messages"):
            return {"data": scenario.get("messages", [])}
        raise AssertionError(f"unexpected URL {url}")
    return _fake


def fresh(scenario, phone=TEST_PHONE):
    """New app + temp DB + stubs for one scenario. Returns (client, get_db, calls)."""
    phone_auth._TEXTBEE_HEALTH_CACHE["at"] = 0.0
    phone_auth._TEXTBEE_HEALTH_CACHE["result"] = None
    tmp = tempfile.mkdtemp(prefix="seediq-guard-test-")
    app, get_db = build(os.path.join(tmp, "t.db"))
    phone_auth._http_get_json = fake_http(scenario)
    calls = []

    def fake_send(digits, message, otp):
        calls.append((digits, len(otp)))
        return True, "stub accepted", "textbee"

    phone_auth.send_sms = fake_send
    return app.test_client(), get_db, calls


def count_codes(get_db):
    with get_db() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM phone_otp").fetchone()["c"]


def main():
    os.environ["SEEDIQ_TEXTBEE_API_KEY"] = "test-key"
    os.environ.pop("SEEDIQ_PHONE_OTP_ECHO", None)
    os.environ.pop("SEEDIQ_SMS_PROVIDER", None)
    os.environ["SEEDIQ_TEXTBEE_DEVICE_ID"] = "dev-1"

    print("=" * 78)
    print("1. Healthy gateway -> request allowed, existing contract intact")
    print("=" * 78)
    c, db, calls = fresh({"devices": [device()], "messages": [msg(10, ack=True)]})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("healthy gateway -> HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("response keeps its documented keys",
          all(k in body for k in ("status", "request_id", "message", "phone",
                                  "otp_length", "expires_in", "provider", "delivery")),
          ",".join(sorted(body.keys())))
    check("code stored and SMS dispatch attempted", count_codes(db) == 1 and len(calls) == 1)

    print("=" * 78)
    print("2. Stale heartbeat alone -> NOT refused (sign-in must keep working)")
    print("=" * 78)
    scenario = {"devices": [device(lastHeartbeat=iso(180))], "messages": []}
    c, db, calls = fresh(scenario)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("stale heartbeat alone -> HTTP 200", r.status_code == 200, f"HTTP {r.status_code}")
    check("code stored and a send attempted", count_codes(db) == 1 and len(calls) == 1,
          f"codes={count_codes(db)} sends={len(calls)}")
    check("response still does NOT claim delivery",
          body.get("delivery") == "accepted", str(body.get("delivery")))
    st = c.get("/api/auth/phone/status").get_json()
    gw = st.get("gateway") or {}
    check("status reports the stale heartbeat honestly",
          st.get("gateway_reachable") is False and gw.get("reason") == "heartbeat_stale",
          f"reachable={st.get('gateway_reachable')} reason={gw.get('reason')}")
    check("status distinguishes 'not proven reachable' from 'send refused'",
          gw.get("send_blocked") is False, str(gw.get("send_blocked")))
    check("heartbeat age is still surfaced for support",
          isinstance(gw.get("last_heartbeat_age_minutes"), (int, float))
          and gw["last_heartbeat_age_minutes"] > 60,
          str(gw.get("last_heartbeat_age_minutes")))

    print("=" * 78)
    print("3. Undelivered backlog -> refused (evidence beats a quiet heartbeat)")
    print("=" * 78)
    scenario = {"devices": [device(lastHeartbeat=iso(180))], "messages": [msg(5, ack=False)]}
    c, db, calls = fresh(scenario)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("unacknowledged message 5 min old -> HTTP 503", r.status_code == 503, f"HTTP {r.status_code}")
    check("error code is sms_gateway_unavailable", body.get("code") == "sms_gateway_unavailable",
          str(body.get("code")))
    check("reason is gateway_not_receiving",
          (body.get("gateway") or {}).get("reason") == "gateway_not_receiving")
    check("recipient in diagnostics is masked, no number leaked",
          str((body.get("gateway") or {}).get("unacknowledged_to", "")).startswith("+91*****"))
    check("no code stored, no SMS dispatched", count_codes(db) == 0 and len(calls) == 0)
    check("503 says no code was sent and nothing queued",
          "no code" in (body.get("message") or "") and "queued" in (body.get("message") or ""),
          body.get("message"))
    st = c.get("/api/auth/phone/status").get_json()
    check("status marks this gateway as send_blocked",
          (st.get("gateway") or {}).get("send_blocked") is True,
          str((st.get("gateway") or {}).get("send_blocked")))

    # Backlog clears (the phone answered the queued message) -> same phone must
    # not be throttled by the earlier refusal.
    scenario["messages"] = [msg(5, ack=True)]
    r2 = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("refused attempt does not burn the cooldown (retry after recovery -> 200)",
          r2.status_code == 200, f"HTTP {r2.status_code}")

    print("=" * 78)
    print("4. Old / acknowledged backlog is ignored")
    print("=" * 78)
    c, db, calls = fresh({"devices": [device()], "messages": [msg(180, ack=False)]})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("3-hour-old unacknowledged message (outside window) -> allowed", r.status_code == 200,
          f"HTTP {r.status_code}")

    print("=" * 78)
    print("4b. Long outage: stale heartbeat + any-age backlog -> refused")
    print("=" * 78)
    # The live case measured on 10-16: a gateway silent for hours, with messages
    # TextBee accepted and it never acknowledged. Every such message is older
    # than the preflight window, so the window rule alone let production answer
    # 200 "accepted" for a code that could only ever arrive expired.
    scenario = {"devices": [device(lastHeartbeat=iso(268))],
                "messages": [msg(123, ack=False), msg(400, ack=False)]}
    c, db, calls = fresh(scenario)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("stale heartbeat + 2 h-old unacknowledged message -> HTTP 503",
          r.status_code == 503, f"HTTP {r.status_code}")
    check("refusal names the real reason, not a configuration error",
          body.get("code") == "sms_gateway_unavailable"
          and (body.get("gateway") or {}).get("reason") == "gateway_not_receiving",
          f"{body.get('code')} / {(body.get('gateway') or {}).get('reason')}")
    check("no code stored and no SMS dispatched",
          count_codes(db) == 0 and len(calls) == 0,
          f"codes={count_codes(db)} sends={len(calls)}")
    check("refusal carries only the masked recipient",
          str((body.get("gateway") or {}).get("unacknowledged_to", "")).startswith("+91*****"),
          str((body.get("gateway") or {}).get("unacknowledged_to")))
    st = c.get("/api/auth/phone/status").get_json()
    check("status marks this gateway send_blocked",
          (st.get("gateway") or {}).get("send_blocked") is True,
          str((st.get("gateway") or {}).get("send_blocked")))

    # Self-healing: once the phone takes the backlog, sends resume with no manual
    # step, no deploy and no operator intervention.
    scenario["messages"] = [msg(123, ack=True), msg(400, ack=True)]
    r2 = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("phone takes the backlog -> the same gateway is allowed again",
          r2.status_code == 200, f"HTTP {r2.status_code}")

    # Signal discipline: neither signal may block on its own.
    c, db, calls = fresh({"devices": [device(lastHeartbeat=iso(268))],
                          "messages": [msg(180, ack=True)]})
    r3 = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("stale heartbeat + only acknowledged history -> allowed",
          r3.status_code == 200, f"HTTP {r3.status_code}")

    c, db, calls = fresh({"devices": [device(lastHeartbeat=iso(268))],
                          "messages": [msg(0.2, ack=False)]})
    r4 = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("unacknowledged but still inside the grace period -> allowed",
          r4.status_code == 200, f"HTTP {r4.status_code}")

    print("=" * 78)
    print("5. Fail-open when the health check itself cannot run")
    print("=" * 78)
    c, db, calls = fresh({"raise": True})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("TextBee API failure -> request still allowed (fail open)", r.status_code == 200,
          f"HTTP {r.status_code}")
    check("code stored and dispatch attempted despite failed health check",
          count_codes(db) == 1 and len(calls) == 1)

    print("=" * 78)
    print("6. Missing / disabled device")
    print("=" * 78)
    c, db, calls = fresh({"devices": [], "messages": []})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("no device at all -> refused",
          r.status_code == 503 and (body.get("gateway") or {}).get("reason") == "no_enabled_device",
          f"HTTP {r.status_code}")
    check("no device -> code sms_no_device, not a reachability claim",
          body.get("code") == "sms_no_device" and "device" in (body.get("message") or ""),
          f"{body.get('code')} / {body.get('message')}")

    c, db, calls = fresh({"devices": [device(enabled=False)], "messages": []})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    check("device disabled -> refused",
          r.status_code == 503 and (body.get("gateway") or {}).get("reason") == "device_disabled",
          f"HTTP {r.status_code}")
    check("disabled device -> code sms_device_disabled",
          body.get("code") == "sms_device_disabled", str(body.get("code")))
    check("every blocking reason maps to its own code",
          {v[0] for v in phone_auth._TEXTBEE_BLOCK_RESPONSES.values()}
          == {"sms_no_device", "sms_device_disabled", "sms_gateway_unavailable"},
          str(sorted(v[0] for v in phone_auth._TEXTBEE_BLOCK_RESPONSES.values())))

    print("=" * 78)
    print("7. Heartbeats disabled -> heartbeat age is not a blocking signal")
    print("=" * 78)
    c, db, calls = fresh({"devices": [device(heartbeatEnabled=False, lastHeartbeat=iso(600))],
                          "messages": []})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("heartbeatEnabled=False + stale heartbeat -> allowed (backlog still checked)",
          r.status_code == 200, f"HTTP {r.status_code}")

    print("=" * 78)
    print("8. Explicit device id is honoured")
    print("=" * 78)
    os.environ["SEEDIQ_TEXTBEE_DEVICE_ID"] = "dev-2"
    c, db, calls = fresh({
        "devices": [device(dev_id="dev-1", lastHeartbeat=iso(600)),
                    device(dev_id="dev-2", lastHeartbeat=iso(2))],
        "messages": [],
    })
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("pinned healthy device chosen over a stale default -> allowed", r.status_code == 200,
          f"HTTP {r.status_code}")

    os.environ["SEEDIQ_TEXTBEE_DEVICE_ID"] = "dev-1"
    c, db, calls = fresh({
        "devices": [device(dev_id="dev-1", lastHeartbeat=iso(600)),
                    device(dev_id="dev-2", lastHeartbeat=iso(2))],
        "messages": [],
    })
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    gw = (c.get("/api/auth/phone/status").get_json().get("gateway") or {})
    check("pinned quiet device is used (never silently swapped) and no longer blocks sign-in",
          r.status_code == 200 and gw.get("device_id") == "dev-1",
          f"HTTP {r.status_code} device={gw.get('device_id')}")
    os.environ["SEEDIQ_TEXTBEE_DEVICE_ID"] = "dev-1"

    print("=" * 78)
    print("9. Local echo mode bypasses the guard (no provider call at all)")
    print("=" * 78)
    os.environ["SEEDIQ_PHONE_OTP_ECHO"] = "1"
    c, db, calls = fresh({"devices": [device(lastHeartbeat=iso(600))], "messages": []})
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("echo mode with stale gateway -> still 200 (dev mode never blocked)",
          r.status_code == 200, f"HTTP {r.status_code}")
    os.environ.pop("SEEDIQ_PHONE_OTP_ECHO", None)

    print()
    print("=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"TEXTBEE GATEWAY GUARD TEST: {passed}/{len(results)} passed")
    print("=" * 78)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
