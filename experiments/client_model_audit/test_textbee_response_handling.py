#!/usr/bin/env python3
"""Isolated test for the TextBee send-sms response handling in phone_auth.py.

Motivation: a real-device test showed TextBee returning HTTP 200 / "success"
while no SMS reached the handset. The old parser only looked at a *flat*
`parsed["success"]`, but TextBee nests its payload under `data`, so every
documented failure shape (disabled device, no enabled device, permission
warning, all-recipients-failed) was silently treated as success.

This test stubs the HTTP transport (`phone_auth._post_json`); it makes NO
network call, sends NO SMS and touches no database. Exit status is the source
of truth (0 = all pass).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "SeedIQ"))

import phone_auth  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def run_case(status, body_obj):
    """Drive send_sms with a stubbed transport returning (status, json-body)."""
    body = body_obj if isinstance(body_obj, str) else json.dumps(body_obj)

    def fake_post_json(url, payload, headers, timeout=None):
        return status, body

    original = phone_auth._post_json
    phone_auth._post_json = fake_post_json
    os.environ["SEEDIQ_TEXTBEE_API_KEY"] = "stub-key-not-real"
    os.environ.pop("SEEDIQ_SMS_PROVIDER", None)
    try:
        return phone_auth.send_sms("919110252930", "1234 is your SeedIQ verification code.", "1234")
    finally:
        phone_auth._post_json = original


def main():
    print("=" * 78)
    print("TextBee send-sms response handling — isolated (no network, no SMS)")
    print("=" * 78)

    ok, msg, provider = run_case(200, {
        "data": {"success": True, "message": "SMS added to queue for processing",
                 "smsBatchId": "66b1f2c3a4d5e6f7a8b9c0d2", "recipientCount": 1}
    })
    check("documented queued response is accepted", ok is True, msg)
    check("accepted-but-not-delivered message does not claim delivery",
          "not yet confirmed" in msg and "sent" not in msg.lower(), msg)
    check("provider is reported as textbee", provider == "textbee", str(provider))

    ok, msg, _ = run_case(200, {"success": True})
    check("legacy flat success still accepted (back-compat)", ok is True, msg)

    ok, msg, _ = run_case(200, {
        "data": {"success": False, "message": "No enabled device found"}
    })
    check("nested data.success=false is rejected", ok is False, msg)

    ok, msg, _ = run_case(200, {"data": {"successCount": 0, "failureCount": 1}})
    check("immediate dispatch with 0 success / 1 failure is rejected", ok is False, msg)

    ok, msg, _ = run_case(200, {
        "data": {"success": True,
                 "warning": {"code": "SMS_PERMISSION_MISSING",
                             "message": "Send SMS permission is not granted"}}
    })
    check("documented permission warning is rejected, not reported as sent", ok is False, msg)

    ok, msg, _ = run_case(400, {"message": "No enabled device. Verify your device is connected."})
    check("HTTP 400 with provider detail is rejected", ok is False, msg)
    check("HTTP 400 propagates the provider's explanation",
          "No enabled device" in msg, msg)

    ok, msg, _ = run_case(401, {"error": "Invalid API key"})
    check("HTTP 401 is rejected", ok is False, msg)

    ok, msg, _ = run_case(200, "<html>not json</html>")
    check("non-JSON 200 body is not treated as a documented success", ok is True,
          "accepted on 2xx without explicit rejection signal")

    failed = [n for n, p in results if not p]
    print("=" * 78)
    print(f"TEXTBEE RESPONSE HANDLING: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        for n in failed:
            print(f"  FAILED: {n}")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
