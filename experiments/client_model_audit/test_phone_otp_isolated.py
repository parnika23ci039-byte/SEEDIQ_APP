#!/usr/bin/env python3
"""Phase 3 — isolated end-to-end test of the SeedIQ phone-OTP flow.

Fully self-contained: a throwaway SQLite file in a temp dir and an in-process
Flask test client. It touches NO production service, sends NO SMS, and never
opens SeedIQ/seediq.db. The real dispatch path is exercised separately
(`send_sms`) — here we assert the *code lifecycle* that surrounds it.

Covers: 4-digit issuance, HMAC-only storage, cooldown, wrong code, attempt
lockout, expiry, success + session establishment, invalid-number rejection.
Exit status is the source of truth (0 = all pass).
"""
import os
import sqlite3
import sys
import tempfile
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "SeedIQ"))

from flask import Flask, session

import phone_auth

SECRET = "test-secret-not-production"
TEST_PHONE = "9110252930"
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


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
        conn.commit()

    # `generate_password_hash` is an INJECTED dependency of register_phone_auth,
    # and this test is about the OTP lifecycle, not werkzeug's KDF. It must be
    # stubbed because every Python on this Mac is 3.9.6 linked against LibreSSL,
    # which does not provide `hashlib.scrypt` — werkzeug's default method — so
    # the real hasher raises AttributeError locally. That is a LOCAL ENVIRONMENT
    # limitation only; production is Linux CPython 3.11.9 on OpenSSL.
    def stub_hash(plaintext):
        return "scrypt$stub$not-a-real-hash"

    phone_auth.register_phone_auth(
        app, get_db, lambda *a, **k: None, stub_hash, SECRET,
        test_mode=False,
    )
    return app, get_db


def main():
    os.environ["SEEDIQ_PHONE_OTP_ECHO"] = "1"  # local echo so we can read the code
    os.environ.pop("SEEDIQ_SMS_PROVIDER", None)
    for k in ("SEEDIQ_TEXTBEE_API_KEY", "TEXTBEE_API_KEY", "SEEDIQ_MSG91_AUTHKEY",
              "TWILIO_ACCOUNT_SID", "SEEDIQ_FAST2SMS_KEY", "SEEDIQ_SMS_WEBHOOK_URL"):
        os.environ.pop(k, None)

    tmp_dir = tempfile.mkdtemp(prefix="seediq-otp-test-")
    tmp_db = os.path.join(tmp_dir, "otp_test.db")
    app, get_db = build(tmp_db)
    c = app.test_client()

    print("=" * 78)
    print("1. Issuance")
    print("=" * 78)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    body = r.get_json()
    code = body.get("debug_code")
    check("request-otp returns 200 in local echo mode", r.status_code == 200, f"HTTP {r.status_code}")
    check("issued code is exactly 4 digits", bool(code) and len(code) == 4 and code.isdigit(), f"code={code}")
    check("response reports otp_length=4", body.get("otp_length") == 4)
    check("response returns a request_id", bool(body.get("request_id")))

    # The server stores the E.164 form ("9110252930" -> "919110252930").
    stored_phone = phone_auth.normalize_phone(TEST_PHONE)
    check("10-digit national number is normalised to E.164 for storage",
          stored_phone == "919110252930", f"stored={stored_phone}")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM phone_otp WHERE phone = ?", (stored_phone,)).fetchone()
    check("code is stored ONLY as an HMAC digest (never clear text)",
          row is not None and row["otp_hash"] != code and len(row["otp_hash"]) == 64,
          f"hash={row['otp_hash'][:16] + '...' if row else 'NO ROW'}")
    check("stored digest matches HMAC(phone:code)",
          bool(row) and row["otp_hash"] == phone_auth.hmac.new(
              SECRET.encode(), f"{stored_phone}:{code}".encode(),
              phone_auth.hashlib.sha256).hexdigest())
    check("no column anywhere holds the clear-text code",
          bool(row) and code not in " ".join(str(row[k]) for k in row.keys()))

    print("\n" + "=" * 78)
    print("2. Cooldown and validation")
    print("=" * 78)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    check("immediate re-request is throttled with 429", r.status_code == 429,
          f"HTTP {r.status_code} code={r.get_json().get('code')}")
    check("throttle reports retry_after", (r.get_json().get("retry_after") or 0) > 0)

    r = c.post("/api/auth/phone/request-otp", json={"phone": "12345"})
    check("invalid phone is rejected 400 invalid_phone",
          r.status_code == 400 and r.get_json().get("code") == "invalid_phone")

    r = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": "12"})
    check("short code rejected 400 invalid_code_format",
          r.status_code == 400 and r.get_json().get("code") == "invalid_code_format")

    r = c.post("/api/auth/phone/verify-otp", json={"phone": "919999999999", "otp": "1234"})
    check("verify with no pending code rejected 400 no_pending_code",
          r.status_code == 400 and r.get_json().get("code") == "no_pending_code")

    print("\n" + "=" * 78)
    print("3. Wrong code / lockout")
    print("=" * 78)
    wrong = "0000" if code != "0000" else "1111"
    r = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": wrong})
    check("wrong code rejected 401 incorrect_code",
          r.status_code == 401 and r.get_json().get("code") == "incorrect_code",
          f"attempts_remaining={r.get_json().get('attempts_remaining')}")
    for _ in range(phone_auth.MAX_ATTEMPTS):
        r = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": wrong})
    check(f"lockout after MAX_ATTEMPTS={phone_auth.MAX_ATTEMPTS} wrong tries (429 too_many_attempts)",
          r.status_code == 429 and r.get_json().get("code") == "too_many_attempts")
    with get_db() as conn:
        left = conn.execute("SELECT COUNT(*) n FROM phone_otp WHERE phone = ?", (stored_phone,)).fetchone()["n"]
    check("locked-out record is deleted (must request a fresh code)", left == 0)

    print("\n" + "=" * 78)
    print("4. Expiry")
    print("=" * 78)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    exp_code = r.get_json().get("debug_code")
    with get_db() as conn:
        conn.execute("UPDATE phone_otp SET expires_at = ? WHERE phone = ?",
                     ((datetime.datetime.now() - datetime.timedelta(seconds=5))
                      .strftime("%Y-%m-%d %H:%M:%S"), stored_phone))
        conn.commit()
    r = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": exp_code})
    check("expired code rejected 400 expired (checked before the hash)",
          r.status_code == 400 and r.get_json().get("code") == "expired")

    print("\n" + "=" * 78)
    print("5. Happy path — correct code establishes a session")
    print("=" * 78)
    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    good = r.get_json().get("debug_code")
    r = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": good})
    body = r.get_json()
    check("correct code accepted (200/201)", r.status_code in (200, 201), f"HTTP {r.status_code}")
    check("first-time phone creates the account", body.get("created") is True)
    check("response carries the authenticated user",
          bool(body.get("user", {}).get("id")) and body["user"]["provider"] == "phone_otp")
    check("the configured admin phone is granted the Admin role",
          body["user"]["role"] == "Admin",
          f"role={body['user']['role']} (SEEDIQ_ADMIN_PHONE default is this number)")
    with c.session_transaction() as sess:
        check("server-side session is established",
              sess.get("user_id") == body["user"]["id"] and sess.get("auth_provider") == "phone_otp",
              f"session keys={sorted(k for k in sess.keys())}")
    with get_db() as conn:
        used = conn.execute("SELECT COUNT(*) n FROM phone_otp WHERE phone = ?", (stored_phone,)).fetchone()["n"]
    check("consumed code is deleted after success", used == 0)

    r = c.post("/api/auth/phone/request-otp", json={"phone": TEST_PHONE, "purpose": "login"})
    r2 = c.post("/api/auth/phone/verify-otp", json={"phone": TEST_PHONE, "otp": r.get_json().get("debug_code")})
    check("second sign-in reuses the existing account (created=False)",
          r2.get_json().get("created") is False)

    # A different number must NOT inherit the admin binding.
    other = "919876543210"
    r = c.post("/api/auth/phone/request-otp", json={"phone": other, "purpose": "login"})
    r3 = c.post("/api/auth/phone/verify-otp",
                json={"phone": other, "otp": r.get_json().get("debug_code")})
    b3 = r3.get_json() or {}
    check("a non-admin number is created with the Farmer role",
          r3.status_code in (200, 201) and b3.get("user", {}).get("role") == "Farmer",
          f"HTTP {r3.status_code} role={b3.get('user', {}).get('role')}")

    print("\n" + "=" * 78)
    print("6. Provider truthfulness — no simulated success")
    print("=" * 78)
    os.environ.pop("SEEDIQ_PHONE_OTP_ECHO", None)  # echo OFF == production behaviour
    app2, get_db2 = build(os.path.join(tmp_dir, "otp_test2.db"))
    c2 = app2.test_client()
    r = c2.post("/api/auth/phone/request-otp", json={"phone": "919876543210"})
    check("with no provider configured the request is REFUSED, not faked",
          r.status_code == 503 and r.get_json().get("code") == "sms_provider_not_configured",
          f"HTTP {r.status_code}")
    check("no code is left behind when dispatch is impossible",
          r.get_json().get("debug_code") is None)

    ok, msg, provider = phone_auth.send_sms("919876543210", "msg", "1234")
    check("send_sms reports failure honestly with no provider", ok is False and provider is None,
          msg[:60])

    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"PHONE OTP ISOLATED TEST: {passed}/{len(results)} passed")
    for name, ok, _ in results:
        if not ok:
            print(f"  !! FAILED: {name}")
    print("=" * 78)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
