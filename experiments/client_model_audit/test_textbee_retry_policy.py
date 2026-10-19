#!/usr/bin/env python3
"""TextBee bounded-retry policy — isolated test (no network, no SMS, no DB).

Motivation: the OTP delay post-mortem showed two distinct failure modes that the
old single-shot send could not tell apart:

  1. a transient provider error (429/5xx) lost the code outright, because the
     send was never retried, and
  2. a retry that cannot prove the first attempt did not land risks handing the
     user two different codes, so a blind resend is not acceptable either.

`send_sms_detailed` answers this with a bounded retry that fires ONLY for
statuses proving the message was not queued (408/425/429/5xx), and a transport
error or unreadable body that consults TextBee's own message history before
deciding. This test pins that behaviour:

  * retryable status -> retried, identical payload, bounded by SEEDIQ_SMS_MAX_RETRIES
  * non-retryable status -> no retry at all
  * transport error    -> NO blind resend; history decides resend / UNKNOWN
  * "accepted" never claims delivery

Stubs: `phone_auth._post_json` (transport), `phone_auth._textbee_recent_send_exists`
(the provider's message history) and `time.sleep` (backoff recording).
Exit status is the source of truth (0 = all pass).
"""
import io
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "SeedIQ"))

import phone_auth  # noqa: E402

TEST_PHONE = "919110252930"
TEST_CODE = "4321"
TEST_MESSAGE = "4321 is your SeedIQ verification code."

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def http_error(code, detail="", retry_after=None):
    """A real urllib HTTPError, so the production `except HTTPError` path runs."""
    err = urllib.error.HTTPError(
        "https://api.textbee.dev/api/v1/gateway/send-sms", code, "stub",
        {}, io.BytesIO(detail.encode()),
    )
    if retry_after is not None:
        err.headers = {"Retry-After": str(retry_after)}
    return err


def transport_error(kind="URLError"):
    if kind == "timeout":
        return TimeoutError("socket timed out")
    return urllib.error.URLError("connection reset by peer")


class Harness:
    """Drives send_sms_detailed with a scripted transport and fake history.

    Script entries are either an exception instance (raised by the stub
    transport) or a (status, body) tuple (returned by it). The last entry
    repeats once the script is exhausted.
    """

    def __init__(self, script, history=False, max_retries=None):
        self.script = list(script)
        self.history = history              # what the provider's history reports
        self.posts = []                     # every payload actually attempted
        self.history_calls = []
        self.sleeps = []
        self.max_retries = max_retries

    def __enter__(self):
        self._post_json = phone_auth._post_json
        self._recent = phone_auth._textbee_recent_send_exists
        self._sleep = phone_auth.time.sleep
        self._env = {k: os.environ.get(k) for k in (
            "SEEDIQ_TEXTBEE_API_KEY", "SEEDIQ_SMS_PROVIDER", "SEEDIQ_SMS_MAX_RETRIES",
            "SEEDIQ_MSG91_AUTHKEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
            "SEEDIQ_FAST2SMS_KEY", "SEEDIQ_SMS_WEBHOOK_URL",
        )}
        for key in ("SEEDIQ_MSG91_AUTHKEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
                    "SEEDIQ_FAST2SMS_KEY", "SEEDIQ_SMS_WEBHOOK_URL", "SEEDIQ_SMS_PROVIDER"):
            os.environ.pop(key, None)
        os.environ["SEEDIQ_TEXTBEE_API_KEY"] = "stub-key-not-real"
        if self.max_retries is None:
            os.environ.pop("SEEDIQ_SMS_MAX_RETRIES", None)
        else:
            os.environ["SEEDIQ_SMS_MAX_RETRIES"] = str(self.max_retries)

        def fake_post_json(url, payload, headers, timeout=None):
            self.posts.append(json.loads(json.dumps(payload)))
            step = self.script[min(len(self.posts) - 1, len(self.script) - 1)]
            if isinstance(step, BaseException):
                raise step
            return step

        def fake_recent_send_exists(digits, since_epoch, slack_seconds=20.0):
            self.history_calls.append(digits)
            return self.history

        def fake_sleep(seconds):
            self.sleeps.append(seconds)

        phone_auth._post_json = fake_post_json
        phone_auth._textbee_recent_send_exists = fake_recent_send_exists
        phone_auth.time.sleep = fake_sleep
        return self

    def __exit__(self, *exc):
        phone_auth._post_json = self._post_json
        phone_auth._textbee_recent_send_exists = self._recent
        phone_auth.time.sleep = self._sleep
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False

    def send(self):
        return phone_auth.send_sms_detailed(TEST_PHONE, TEST_MESSAGE, TEST_CODE)

    @property
    def payloads_identical(self):
        return all(p == self.posts[0] for p in self.posts) and bool(self.posts)


QUEUED = (200, json.dumps({"data": {"success": True, "message": "SMS added to queue"}}))


def main():
    print("=" * 78)
    print("TextBee bounded-retry policy — isolated (no network, no SMS)")
    print("=" * 78)

    # 1. A transient 503 is retried, and the retry carries the SAME code.
    with Harness([http_error(503, "upstream unavailable"), QUEUED]) as h:
        state, msg, provider = h.send()
    check("retryable 503 is retried (2 attempts)", len(h.posts) == 2, f"posts={len(h.posts)}")
    check("retried attempt reuses the identical payload (one code only)",
          h.payloads_identical, json.dumps(h.posts[0].get("message")))
    check("503-then-success reports ACCEPTED, not a failure",
          state == phone_auth.SMS_STATE_ACCEPTED and provider == "textbee", f"{state}/{provider}")
    check("ACCEPTED does not claim delivery", "not yet confirmed" in msg, msg)

    # 2. Retries are bounded: default 2 extra attempts => 3 posts, then FAILED.
    with Harness([http_error(500, "boom")]) as h:
        state, msg, _ = h.send()
    check("persistent 5xx retries are bounded (default 3 attempts total)",
          len(h.posts) == 3, f"posts={len(h.posts)}")
    check("exhausted retries report FAILED honestly",
          state == phone_auth.SMS_STATE_FAILED, f"{state}: {msg}")
    check("exhausted retries explain the provider's own status",
          "500" in msg, msg)

    # 3. The bound is configurable, and a silly value is clamped.
    with Harness([http_error(500, "boom")], max_retries=0) as h:
        h.send()
    check("SEEDIQ_SMS_MAX_RETRIES=0 disables retrying", len(h.posts) == 1, f"posts={len(h.posts)}")

    with Harness([http_error(500, "boom")], max_retries=99) as h:
        h.send()
    check("SEEDIQ_SMS_MAX_RETRIES is clamped (<=4 extra => 5 attempts)",
          len(h.posts) == 5, f"posts={len(h.posts)}")

    # 4. A status that does NOT prove the message was dropped is never retried.
    with Harness([http_error(400, "No enabled device. Verify your device is connected.")]) as h:
        state, msg, _ = h.send()
    check("HTTP 400 is not retried (may already be queued elsewhere)",
          len(h.posts) == 1, f"posts={len(h.posts)}")
    check("HTTP 400 is reported as FAILED, not accepted",
          state == phone_auth.SMS_STATE_FAILED and "No enabled device" in msg, msg)

    with Harness([http_error(401, "Invalid API key")]) as h:
        state, msg, _ = h.send()
    check("HTTP 401 is not retried and is FAILED",
          len(h.posts) == 1 and state == phone_auth.SMS_STATE_FAILED, f"posts={len(h.posts)}: {msg}")

    # 5. Rate limiting: retried, honours Retry-After, backoff stays bounded.
    with Harness([http_error(429, "slow down", retry_after=2), QUEUED]) as h:
        state, _, _ = h.send()
    check("HTTP 429 is retried", len(h.posts) == 2, f"posts={len(h.posts)}")
    check("Retry-After is honoured for the retry sleep",
          h.sleeps and max(h.sleeps) >= 2, f"sleeps={h.sleeps}")
    check("retry sleep is capped (a rate-limited gateway is not hammered)",
          all(s <= phone_auth.SMS_RETRY_MAX_SLEEP_SECONDS for s in h.sleeps), f"sleeps={h.sleeps}")
    check("429-then-success reports ACCEPTED", state == phone_auth.SMS_STATE_ACCEPTED, state)

    # 5b. A huge Retry-After cannot stall the request handler indefinitely.
    with Harness([http_error(429, "slow down", retry_after=600), QUEUED]) as h:
        h.send()
    check("an absurd Retry-After is capped by the shared sleep bound",
          h.sleeps and max(h.sleeps) <= phone_auth.SMS_RETRY_MAX_SLEEP_SECONDS, f"sleeps={h.sleeps}")

    # 6. Transport error + history proves the message landed => NO resend.
    with Harness([transport_error()], history=True) as h:
        state, msg, _ = h.send()
    check("transport error is NOT resent blind when history confirms the send",
          len(h.posts) == 1, f"posts={len(h.posts)}")
    check("duplicate-safety is decided by the provider's own history",
          len(h.history_calls) == 1, f"history_calls={len(h.history_calls)}")
    check("history-confirmed transport error reports ACCEPTED with unconfirmed delivery",
          state == phone_auth.SMS_STATE_ACCEPTED and "not confirmed" in msg, msg)

    # 7. Transport error + unreadable history => UNKNOWN, still no resend.
    with Harness([transport_error()], history=None) as h:
        state, msg, _ = h.send()
    check("transport error with unreadable history does not resend",
          len(h.posts) == 1, f"posts={len(h.posts)}")
    check("unprovable outcome is reported UNKNOWN, not FAILED",
          state == phone_auth.SMS_STATE_UNKNOWN, f"{state}: {msg}")
    check("UNKNOWN tells the caller nothing was resent", "nothing was resent" in msg, msg)
    with Harness([transport_error()], history=None) as h:
        ok, _, _ = phone_auth.send_sms(TEST_PHONE, TEST_MESSAGE, TEST_CODE)
    check("back-compat send_sms() reports ok=True for UNKNOWN (never a fake hard failure)",
          ok is True, str(ok))

    # 8. Transport error + readable history WITHOUT the message => resend allowed.
    with Harness([transport_error()], history=False) as h:
        state, msg, _ = h.send()
    check("transport error with history proving nothing was queued may resend",
          len(h.posts) == 3, f"posts={len(h.posts)}")
    check("resend reuses the identical code", h.payloads_identical, json.dumps(h.posts[0].get("message")))
    check("history-checked-but-never-landed ends as FAILED",
          state == phone_auth.SMS_STATE_FAILED, f"{state}: {msg}")

    # 9. Unreadable 2xx body is not treated as acceptance (the old bug).
    with Harness([(200, "<html>not json</html>")], history=False) as h:
        state, msg, _ = h.send()
    check("unreadable 200 body is not accepted on faith",
          state == phone_auth.SMS_STATE_FAILED, f"{state}: {msg}")
    check("unreadable body consults provider history", len(h.history_calls) >= 1,
          f"history_calls={len(h.history_calls)}")

    with Harness([(200, "<html>not json</html>")], history=True) as h:
        state, msg, _ = h.send()
    check("unreadable 200 body confirmed by history is ACCEPTED, not resent",
          state == phone_auth.SMS_STATE_ACCEPTED and len(h.posts) == 1,
          f"{state} posts={len(h.posts)}")

    with Harness([(200, "<html>not json</html>")], history=None) as h:
        state, msg, _ = h.send()
    check("unreadable body with unreadable history is UNKNOWN and never resent",
          state == phone_auth.SMS_STATE_UNKNOWN and len(h.posts) == 1,
          f"{state} posts={len(h.posts)}")

    # 10. Every terminal message that claims acceptance says delivery is unconfirmed.
    accepted_msgs = []
    for script in ([QUEUED], [http_error(503, "x"), QUEUED], [transport_error()]):
        with Harness(script, history=True) as h:
            state, msg, _ = h.send()
        if state == phone_auth.SMS_STATE_ACCEPTED:
            accepted_msgs.append(msg)
    check("no ACCEPTED message ever claims the SMS was delivered",
          accepted_msgs and all(
              ("not confirmed" in m or "not yet confirmed" in m) and "delivered" not in m.lower()
              for m in accepted_msgs),
          f"{len(accepted_msgs)} accepted messages checked")

    failed = [n for n, ok, _ in results if not ok]
    print("=" * 78)
    print(f"TEXTBEE RETRY POLICY: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        for n in failed:
            print(f"  FAILED: {n}")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
