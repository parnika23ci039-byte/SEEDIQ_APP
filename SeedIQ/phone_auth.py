"""
SeedIQ — phone-number authentication with a 4-digit verification code.

WHY THIS FILE EXISTS
--------------------
The client requires the phone number to be the primary user identifier, with a
4-digit verification code. The original backend only knew email + password
(`/api/login`, `/api/register/request-otp` -> Resend e-mail), so a phone flow
could not be honest without real server-side support. This module adds it.

DESIGN NOTES
------------
* No secrets in the mobile app. The SMS provider is chosen purely from
  server-side environment variables; the phone never sees a provider key.
* Codes are 4 digits and are stored only as an HMAC-SHA256 digest, never in
  clear text, never returned to the caller.
* Both "sign in" and "create account" go through the same verify endpoint —
  a first-time phone is registered, a known phone is signed in. That is what
  the client asked for ("phone number is the only login identifier").
* Nothing here is simulated: if no SMS provider is configured the request is
  refused with `sms_provider_not_configured` instead of pretending to send.

ENVIRONMENT
-----------
    SEEDIQ_DEFAULT_COUNTRY_CODE   default "91" (India)
    SEEDIQ_ADMIN_PHONE            default "919110252930"
    SEEDIQ_ADMIN_PHONE_EMAIL      default "parnikaaa14@gmail.com"
    SEEDIQ_PHONE_OTP_TTL_SECONDS  default 300
    SEEDIQ_PHONE_OTP_COOLDOWN     default 20
    SEEDIQ_PHONE_OTP_ECHO         "1" -> echo the code in the response.
                                  LOCAL DEVELOPMENT ONLY, never in production.
    SEEDIQ_SMS_PROVIDER           force one of: textbee | msg91 | twilio | fast2sms | webhook

    TextBee:  SEEDIQ_TEXTBEE_API_KEY (or TEXTBEE_API_KEY),
              SEEDIQ_TEXTBEE_DEVICE_ID (optional; default device is used if omitted),
              SEEDIQ_TEXTBEE_BASE_URL (optional; default https://api.textbee.dev),
              SEEDIQ_SMS_MAX_RETRIES (default 2) — bounded extra attempts, used
                ONLY for failures that prove the provider did not queue the
                message (HTTP 408/425/429/5xx). A transport timeout is never
                resent blindly: the provider's own message history is consulted
                first, so a duplicate SMS cannot be produced,
              SEEDIQ_TEXTBEE_DELIVERY_PROBE_SECONDS (default 1.2, 0 disables) —
                how long to wait after acceptance before asking TextBee whether
                the gateway phone actually took the message,
              SEEDIQ_TEXTBEE_PREFLIGHT_GRACE_SECONDS (default 90) — a dispatched
                message unacknowledged for longer than this means the gateway
                phone is not receiving pushes (Doze/battery), so new codes are
                refused instead of queued,
              SEEDIQ_TEXTBEE_PREFLIGHT_WINDOW_SECONDS (default 3600) — only
                messages requested within this window refuse on their own; a
                stale heartbeat together with any-age unacknowledged message
                also refuses (see the preflight block comment),
              SEEDIQ_TEXTBEE_PREFLIGHT_DISPATCH_TIMEOUT_SECONDS (default 900,
                0 disables) — a recent message that TextBee had to re-dispatch,
                or that carries the provider's "no response from device" error,
                proves the gateway ignored the push (the 9-170 min delays
                measured 10-11 .. 10-15), so new codes are refused
    MSG91:    SEEDIQ_MSG91_AUTHKEY, SEEDIQ_MSG91_TEMPLATE_ID,
              SEEDIQ_MSG91_SENDER (optional), SEEDIQ_MSG91_OTP_VAR (default OTP)
    Twilio:   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM
    Fast2SMS: SEEDIQ_FAST2SMS_KEY
    Webhook:  SEEDIQ_SMS_WEBHOOK_URL, SEEDIQ_SMS_WEBHOOK_TOKEN (optional)
"""

from __future__ import annotations

import datetime
import hmac
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import jsonify, request, session

OTP_LENGTH = 4
OTP_MIN = 10 ** (OTP_LENGTH - 1)
OTP_SPAN = 9 * 10 ** (OTP_LENGTH - 1)
MAX_ATTEMPTS = 5
SMS_TIMEOUT_SECONDS = 12

# Bounded, duplicate-safe retry policy for the TextBee send call. Every attempt
# reuses the identical payload (same code), so even in the worst case a retry
# cannot hand the user a second, different code.
SMS_MAX_EXTRA_ATTEMPTS_DEFAULT = 2
SMS_RETRY_BASE_SECONDS = 0.75
SMS_RETRY_MAX_SLEEP_SECONDS = 3.0

# Statuses that prove the message was NOT queued, so a resend is safe.
_TEXTBEE_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# After the provider accepts, how long to wait before asking it whether the
# gateway phone took the message (bounded; only affects the response wording).
DELIVERY_PROBE_GRACE_DEFAULT_SECONDS = 1.2

# Honest dispatch states. "accepted" is NOT delivery: TextBee queues the message
# to the Android gateway and answers 200 before the phone has sent anything.
SMS_STATE_ACCEPTED = "accepted"      # provider queued it (delivery unconfirmed)
SMS_STATE_UNKNOWN = "unknown"        # provider could neither confirm nor deny
SMS_STATE_FAILED = "failed"          # provably not queued
SMS_STATE_NOT_CONFIGURED = "not_configured"

_E164 = re.compile(r"^[1-9]\d{7,14}$")
_INDIA_MOBILE = re.compile(r"^[6-9]\d{9}$")


# ---------------------------------------------------------------------------
# Phone normalisation
# ---------------------------------------------------------------------------

def default_country_code() -> str:
    return re.sub(r"\D", "", os.environ.get("SEEDIQ_DEFAULT_COUNTRY_CODE", "91")) or "91"


def normalize_phone(raw, country_code: str | None = None) -> str | None:
    """
    Return the MSISDN in E.164 *without* the leading '+', or None if invalid.

    Accepts the shapes an Indian user actually types:
        "9110252930", "09110252930", "+91 91102 52930", "0091-9110252930",
        "+919110252930", and full international numbers.
    """
    if raw is None:
        return None
    digits = re.sub(r"[^\d+]", "", str(raw))
    if not digits:
        return None
    if digits.startswith("+"):
        digits = digits[1:]
    elif digits.startswith("00"):
        digits = digits[2:]
    digits = re.sub(r"\D", "", digits)
    if not digits:
        return None

    cc = country_code or default_country_code()

    # National trunk prefix: 0xxxxxxx (only when the result stays plausible).
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    if len(digits) == 10:
        digits = cc + digits
    elif len(digits) == 12 and digits.startswith("0" + cc):
        digits = cc + digits[2:]

    if not _E164.match(digits):
        return None

    # India-specific sanity check so a typo is caught before an SMS is billed.
    if digits.startswith("91") and not _INDIA_MOBILE.match(digits[2:]):
        return None

    return digits


def pretty_phone(digits: str) -> str:
    """"+91 91102 52930" for display; falls back to "+<digits>"."""
    if digits.startswith("91") and len(digits) == 12:
        n = digits[2:]
        return f"+91 {n[:5]} {n[5:]}"
    return "+" + digits


def masked_phone(digits: str) -> str:
    """Log-safe reference that still identifies the line: '+91*****2930'."""
    if len(digits) <= 6:
        return "+*****"
    return "+" + digits[:2] + "*****" + digits[-4:]


def synthetic_email(digits: str) -> str:
    """Stable unique e-mail for a phone-only account (never used for delivery)."""
    return f"{digits}@phone.seediq.app"


# ---------------------------------------------------------------------------
# SMS delivery providers (server-side only)
# ---------------------------------------------------------------------------

def _textbee_api_key() -> str:
    return (
        os.environ.get("SEEDIQ_TEXTBEE_API_KEY")
        or os.environ.get("TEXTBEE_API_KEY")
        or ""
    ).strip()


def _textbee_base_url() -> str:
    return (
        os.environ.get("SEEDIQ_TEXTBEE_BASE_URL")
        or os.environ.get("TEXTBEE_BASE_URL")
        or "https://api.textbee.dev"
    ).strip().rstrip("/")


def _textbee_device_id() -> str:
    return (
        os.environ.get("SEEDIQ_TEXTBEE_DEVICE_ID")
        or os.environ.get("TEXTBEE_DEVICE_ID")
        or ""
    ).strip()


# Cloudflare (api.textbee.dev) bans urllib's default User-Agent with 403 error
# 1010; every call to that host must send a browser-style one.
_TEXTBEE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# TextBee gateway preflight
# ---------------------------------------------------------------------------
# The gateway is an Android phone. TextBee's API accepts a send even when that
# phone is unreachable (Doze / battery restrictions), and the message then sits
# in the cloud until the phone next wakes. Measured on 10-11: codes requested at
# 20:09-20:13 IST reached the handsets at 01:00:31 IST (~5 h later), long after
# the 5-minute TTL - so the user saw "sent" and could never use the code.
#
# The preflight below reports how the gateway looks and refuses to queue a new
# code ONLY when there is concrete evidence the phone cannot take the message.
# It is never allowed to block sign-in by accident:
#
#   ok=True   -> there is proof the gateway is receiving (fresh heartbeat and no
#                unanswered push in its backlog)
#   ok=False  -> no such proof; whether a send is refused depends on the reason
#                (only the reasons in _TEXTBEE_BLOCKING_REASONS refuse)
#   ok=None   -> the health check itself failed; callers fail OPEN
#
# A stale heartbeat is a HEALTH SIGNAL, not a send gate: TextBee documents that
# "the API still accepts sends for it, and the messages wait until the phone
# comes back"
# (https://textbee.dev/docs/troubleshooting/messages-not-sending) and its device
# guide treats lastHeartbeat as a health indicator, not an online/offline switch.
# Hard-refusing on heartbeat age alone took sign-in down on 10-15/10-16 - the
# gateway heartbeat was 2 h stale while the device was enabled and out of Doze,
# and every login was answered with 503 instead of a queued code.
#
# Thresholds: a fresh heartbeat is one younger than max(45 min,
# 2x heartbeatIntervalMinutes); an "unreceived" message is one handed to the
# push service (TextBee accepted it) with no pushReceivedAt, after a grace
# period (default 90 s; the healthy baseline on this account is 0-30 s).
#
# Two signals together are treated as proof that the phone is not taking
# messages, and refuse the send: a stale heartbeat AND an accepted message it
# has never acknowledged (any age). Either signal alone stays non-blocking, so a
# quiet-but-working gateway is never refused; the window limit below applies to
# the backlog signal on its own, because during a multi-hour outage every stuck
# message is older than any window the service might pick.
_TEXTBEE_HEALTH_CACHE: dict = {"at": 0.0, "result": None}

# Reasons that justify refusing a send. Only concrete evidence belongs here: a
# missing or disabled device (TextBee itself rejects those with HTTP 400), or a
# recent message that TextBee handed to the push service and the phone never
# acknowledged. Heartbeat age is reported but is deliberately NOT in this set -
# see the block comment above.
_TEXTBEE_BLOCKING_REASONS = frozenset({
    "no_enabled_device",
    "device_disabled",
    "gateway_not_receiving",
})

# One accurate, actionable answer per blocking reason, so the client can show the
# real cause instead of a blanket "SMS service is not configured". The reason is
# also echoed in the `gateway` detail block of the response.
_TEXTBEE_BLOCK_RESPONSES = {
    "no_enabled_device": (
        "sms_no_device",
        "No SMS gateway device is enabled on the TextBee account, so no code was "
        "sent. Ask an administrator to enable the gateway device.",
    ),
    "device_disabled": (
        "sms_device_disabled",
        "The SMS gateway device is disabled, so no code was sent. Ask an "
        "administrator to enable the gateway device.",
    ),
    "gateway_not_receiving": (
        "sms_gateway_unavailable",
        "The SMS gateway phone is not reachable right now, so no code was sent "
        "and nothing was queued. Please try again in a few minutes.",
    ),
}


def _http_get_json(url: str, params: dict | None = None, timeout: int = 6) -> dict:
    """Single GET choke point for TextBee diagnostics (monkeypatched in tests)."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("x-api-key", _textbee_api_key())
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", _TEXTBEE_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    """Read a numeric env knob; an empty or malformed value falls back."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def _sms_max_extra_attempts() -> int:
    raw = (os.environ.get("SEEDIQ_SMS_MAX_RETRIES") or "").strip()
    if not raw:
        return SMS_MAX_EXTRA_ATTEMPTS_DEFAULT
    try:
        return max(0, min(int(raw), 4))
    except ValueError:
        return SMS_MAX_EXTRA_ATTEMPTS_DEFAULT


def _delivery_probe_grace_seconds() -> float:
    return _env_float("SEEDIQ_TEXTBEE_DELIVERY_PROBE_SECONDS", DELIVERY_PROBE_GRACE_DEFAULT_SECONDS)


def _sleep_before_retry(attempt: int, retry_after: float | None) -> None:
    """Bounded exponential backoff; honour a Retry-After up to the same cap."""
    delay = SMS_RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1))
    if retry_after is not None:
        delay = max(delay, retry_after)
    time.sleep(min(delay, SMS_RETRY_MAX_SLEEP_SECONDS))


def _http_error_detail(exc) -> str:
    try:
        return (exc.read() or b"").decode("utf-8", "replace")[:200]
    except Exception:
        return ""


def _retry_after_seconds(exc) -> float | None:
    try:
        raw = (exc.headers or {}).get("Retry-After")
    except Exception:
        raw = None
    if raw is None:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return None


def _textbee_digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _textbee_fetch_sent_messages(limit: int = 20) -> list:
    """Newest-first slice of the messages TextBee dispatched (GET only)."""
    return _http_get_json(
        f"{_textbee_base_url()}/api/v1/gateway/messages",
        {"direction": "sent", "limit": max(1, min(limit, 50)), "order": "desc"},
    ).get("data") or []


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


def _textbee_recent_send_exists(
    digits: str, since_epoch: float, slack_seconds: float = 20.0
) -> bool | None:
    """
    Did TextBee really take a message for `digits` around/after `since_epoch`?

    True  -> a matching sent message exists: the request DID land, do not resend
    False -> the history is readable and holds no such message: safe to resend
    None  -> the history could not be read: outcome unknown, never resend

    This is what makes the retry policy duplicate-safe: a transport error never
    triggers a blind resend, the provider's own record decides.
    """
    try:
        rows = _textbee_fetch_sent_messages()
    except Exception:
        return None
    cutoff = datetime.datetime.fromtimestamp(
        since_epoch - max(0.0, slack_seconds), tz=datetime.timezone.utc
    )
    for m in rows:
        if not isinstance(m, dict) or _textbee_digits(m.get("recipient")) != digits:
            continue
        requested = _parse_iso(m.get("requestedAt") or m.get("createdAt"))
        if requested is None:
            continue
        if _as_utc(requested) >= cutoff:
            return True
    return False


def _dispatch_timed_out(m: dict) -> bool:
    """TextBee's own record of a push the gateway phone ignored."""
    attempts = m.get("dispatchAttempts")
    if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts >= 2:
        return True
    text = f"{m.get('errorMessage') or ''} {m.get('errorCode') or ''}".lower()
    return "no response from device" in text or "status update timeout" in text


def _textbee_recent_delivery_warnings(
    rows: list, window_hours: float = 6.0, sample: int = 6
) -> dict:
    """
    How late are codes actually arriving right now?

    Built from the gateway's own history: for the last few messages, the
    requestedAt -> pushReceivedAt gap. Measured baselines: 0-30 s when the phone
    is awake, 9-170 min when it is dozing (10-11 .. 10-15 records).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    latencies = []
    for m in rows[: max(1, sample)]:
        if not isinstance(m, dict):
            continue
        requested = _parse_iso(m.get("requestedAt") or m.get("createdAt"))
        push = _parse_iso(m.get("pushReceivedAt"))
        if requested is None or push is None:
            continue
        if (now - _as_utc(requested)).total_seconds() > window_hours * 3600:
            continue
        latencies.append(max(0.0, (_as_utc(push) - _as_utc(requested)).total_seconds()))
    if not latencies:
        return {}
    return {
        "recent_gateway_ack_seconds": round(max(latencies), 1),
        "recent_deliveries_sampled": len(latencies),
        "recent_slow_deliveries": len([s for s in latencies if s >= 60.0]),
    }


def probe_textbee_delivery(digits: str, since_epoch: float) -> dict:
    """
    Read back the provider's own record for a message just accepted.

    Bounded, best effort, GET only. Returns {} when nothing can be determined.
    Message bodies are never returned or logged (they are the OTP); only the
    provider's timestamps, counts and its own status/error strings are exposed.

    `state`:
      handed_to_carrier   -> the gateway handed the SMS to the SIM/carrier
      dispatched_to_phone -> the gateway phone acknowledged the push
      queued_on_gateway   -> accepted and queued, the phone has not taken it yet
      unknown             -> no visible record yet (never claim delivery)
    """
    try:
        rows = _textbee_fetch_sent_messages()
    except Exception:
        return {}
    cutoff = datetime.datetime.fromtimestamp(since_epoch - 20.0, tz=datetime.timezone.utc)
    match = None
    requested = None
    for m in rows:
        if not isinstance(m, dict) or _textbee_digits(m.get("recipient")) != digits:
            continue
        requested = _parse_iso(m.get("requestedAt") or m.get("createdAt"))
        if requested is None:
            continue
        if _as_utc(requested) >= cutoff:
            match = m
            break
    if match is None or requested is None:
        return {"state": "unknown", "found": False}

    requested = _as_utc(requested)
    push = _parse_iso(match.get("pushReceivedAt"))
    sent = _parse_iso(match.get("sentAt"))
    if sent:
        state = "handed_to_carrier"
    elif push:
        state = "dispatched_to_phone"
    else:
        state = "queued_on_gateway"
    error = match.get("errorMessage") or match.get("errorCode")
    attempts = match.get("dispatchAttempts")
    out = {
        "state": state,
        "found": True,
        "provider_status": match.get("status"),
        "gateway_ack_seconds": round((_as_utc(push) - requested).total_seconds(), 1) if push else None,
        "dispatch_attempts": attempts if isinstance(attempts, int) and not isinstance(attempts, bool) else None,
        "provider_error": str(error)[:120] if error else None,
    }
    out.update(_textbee_recent_delivery_warnings(rows))
    return out


def _parse_iso(value) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _preflight_grace_seconds() -> float:
    try:
        value = float((os.environ.get("SEEDIQ_TEXTBEE_PREFLIGHT_GRACE_SECONDS") or "").strip())
    except ValueError:
        value = 90.0
    return max(30.0, value)


def _preflight_window_seconds() -> float:
    try:
        value = float((os.environ.get("SEEDIQ_TEXTBEE_PREFLIGHT_WINDOW_SECONDS") or "").strip())
    except ValueError:
        value = 3600.0
    return max(300.0, value)


def _preflight_dispatch_timeout_seconds() -> float:
    """Window for the re-dispatch / "no response from device" signal (0 = off)."""
    return _env_float("SEEDIQ_TEXTBEE_PREFLIGHT_DISPATCH_TIMEOUT_SECONDS", 900.0)


def _textbee_gateway_preflight(ttl_seconds: float = 0) -> tuple[bool | None, str, dict]:
    """Check the gateway phone before queueing an OTP. See the block comment."""
    started = time.monotonic()
    cached = _TEXTBEE_HEALTH_CACHE.get("result")
    if cached is not None and ttl_seconds and (started - _TEXTBEE_HEALTH_CACHE["at"]) < ttl_seconds:
        return cached

    try:
        if not _textbee_api_key():
            result: tuple[bool | None, str, dict] = (None, "no_api_key", {})
        else:
            base = f"{_textbee_base_url()}/api/v1/gateway"
            devices = _http_get_json(f"{base}/devices").get("data") or []
            wanted = _textbee_device_id()
            target = next((d for d in devices if wanted and d.get("_id") == wanted), None)
            if target is None:
                enabled = [d for d in devices if d.get("enabled")]
                default = [d for d in enabled if d.get("isDefault")]
                target = (default or enabled or [None])[0]

            if not target:
                result = (False, "no_enabled_device", {"device_count": len(devices)})
            elif not target.get("enabled"):
                result = (False, "device_disabled", {"device_id": target.get("_id")})
            else:
                power = target.get("powerInfo") or {}
                detail = {
                    "device_id": target.get("_id"),
                    "heartbeat_enabled": bool(target.get("heartbeatEnabled")),
                    "battery_optimization_exempt": power.get("isIgnoringBatteryOptimizations"),
                    "doze_mode": power.get("isDeviceIdleMode"),
                }
                # Direct evidence first: a message TextBee handed to the push
                # service that the phone never acknowledged means pushes are not
                # arriving at all. This is the only signal that justifies
                # refusing a send, so it is evaluated whatever the heartbeat says.
                grace = _preflight_grace_seconds()
                window = _preflight_window_seconds()
                rows = _http_get_json(
                    f"{base}/messages",
                    {"direction": "sent", "limit": 20, "order": "desc"},
                ).get("data") or []
                reference = datetime.datetime.now(datetime.timezone.utc)
                blocked = None
                # Same evidence, without the window. During a long outage the
                # window rule above cannot fire at all: every unacknowledged
                # message is by definition older than the window, which is
                # exactly when this proof is needed (measured live 10-16: a
                # 4.5 h-silent gateway with three stuck messages still answered
                # 200 "accepted"). It is only used together with a stale
                # heartbeat, below.
                backlog = None
                for m in rows:
                    if m.get("pushReceivedAt") or m.get("receivedAt"):
                        continue
                    requested = _parse_iso(m.get("requestedAt") or m.get("createdAt"))
                    if not requested:
                        continue
                    age_s = (reference - requested).total_seconds()
                    if age_s < grace:
                        continue
                    candidate = {
                        "unacknowledged_age_seconds": round(age_s, 1),
                        "unacknowledged_to": masked_phone(
                            "".join(ch for ch in str(m.get("recipient") or "") if ch.isdigit())
                        )
                        or "*****",
                    }
                    if age_s <= window:
                        blocked = candidate
                        break
                    if backlog is None:
                        backlog = candidate

                heartbeat = _parse_iso(target.get("lastHeartbeat"))
                if heartbeat:
                    age_min = (
                        datetime.datetime.now(datetime.timezone.utc) - heartbeat
                    ).total_seconds() / 60.0
                    detail["last_heartbeat_age_minutes"] = round(age_min, 1)
                else:
                    age_min = None
                interval = target.get("heartbeatIntervalMinutes")
                max_age = max(45.0, 2.0 * float(interval)) if isinstance(interval, (int, float)) else 45.0
                stale = bool(target.get("heartbeatEnabled")) and (age_min is None or age_min > max_age)

                if blocked is None and stale and backlog is not None:
                    # Two independent signals agree: the phone has not reported in
                    # for over an hour AND TextBee accepted a message that it has
                    # still never acknowledged. A stale heartbeat ALONE must still
                    # not refuse (a quiet gateway can take sends - blocking on
                    # heartbeat age alone took sign-in down on 10-15/10-16), so the
                    # backlog is the missing proof. This clears by itself the
                    # moment the phone takes the queued messages (pushReceivedAt
                    # appears) or heartbeats again.
                    blocked = backlog

                if blocked:
                    detail.update(blocked)
                    result = (False, "gateway_not_receiving", detail)
                elif stale:
                    # Reported, not fatal: the send still goes out and the truth
                    # about delivery comes from the provider's own message record.
                    result = (False, "heartbeat_stale", detail)
                else:
                    result = (True, "ok", detail)
    except Exception as exc:  # the check must never be able to break sign-in
        result = (None, "health_check_failed", {"error": type(exc).__name__})

    _TEXTBEE_HEALTH_CACHE["at"] = started
    _TEXTBEE_HEALTH_CACHE["result"] = result
    return result


def active_sms_provider() -> str | None:
    forced = (os.environ.get("SEEDIQ_SMS_PROVIDER") or "").strip().lower()
    available = []
    if _textbee_api_key():
        available.append("textbee")
    if os.environ.get("SEEDIQ_MSG91_AUTHKEY"):
        available.append("msg91")
    if os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"):
        available.append("twilio")
    if os.environ.get("SEEDIQ_FAST2SMS_KEY"):
        available.append("fast2sms")
    if os.environ.get("SEEDIQ_SMS_WEBHOOK_URL"):
        available.append("webhook")
    if forced:
        return forced if forced in available else None
    return available[0] if available else None


def _post_json(url: str, payload: dict, headers: dict, timeout: int = SMS_TIMEOUT_SECONDS):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        return resp.status, body


def _post_form(url: str, fields: dict, headers: dict, timeout: int = SMS_TIMEOUT_SECONDS):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def send_sms_detailed(digits: str, message: str, otp: str) -> tuple[str, str, str | None]:
    """
    Send `message` to `digits`. Returns (state, human_message, provider).

    `state` is SMS_STATE_ACCEPTED / SMS_STATE_UNKNOWN / SMS_STATE_FAILED /
    SMS_STATE_NOT_CONFIGURED. "accepted" means the provider queued the message
    (TextBee wraps it to its Android gateway); it is never proof that a handset
    or a carrier delivered anything.

    Every branch is a real network call; there is no simulated success path.
    """
    provider = active_sms_provider()
    if not provider:
        return (
            SMS_STATE_NOT_CONFIGURED,
            "No SMS provider is configured on the server. Set SEEDIQ_TEXTBEE_API_KEY "
            "(TextBee Android gateway), MSG91, Twilio, Fast2SMS or SEEDIQ_SMS_WEBHOOK_URL "
            "in the backend environment.",
            None,
        )

    e164 = "+" + digits
    try:
        if provider == "textbee":
            api_key = _textbee_api_key()
            if not api_key:
                return (SMS_STATE_FAILED, "SEEDIQ_TEXTBEE_API_KEY is not configured.", provider)
            payload = {"recipients": [e164], "message": message}
            device_id = _textbee_device_id()
            if device_id:
                payload["deviceId"] = device_id
            url = f"{_textbee_base_url()}/api/v1/gateway/send-sms"
            headers = {
                "x-api-key": api_key,
                "Accept": "application/json",
                "User-Agent": _TEXTBEE_UA,
            }
            extra_attempts = _sms_max_extra_attempts()
            request_started = time.time()
            attempt = 0

            while True:
                attempt += 1
                try:
                    status, body = _post_json(url, payload, headers)
                except urllib.error.HTTPError as e:
                    # 5xx / 429 are transient. Retry only within the bound and
                    # honour Retry-After so a rate-limited gateway is not hammered.
                    detail = _http_error_detail(e)
                    if e.code in _TEXTBEE_RETRYABLE_STATUS and attempt <= extra_attempts:
                        _sleep_before_retry(attempt, _retry_after_seconds(e))
                        continue
                    return (SMS_STATE_FAILED, f"{provider} delivery failed ({e.code}): {detail}", provider)
                except Exception as e:
                    # The request may or may not have reached TextBee. Never
                    # resend blind: ask the provider what it actually holds. If
                    # its history is unreadable the outcome is UNKNOWN, not a
                    # failure — the caller must not pretend it failed.
                    known = _textbee_recent_send_exists(digits, request_started)
                    if known is True:
                        return (
                            SMS_STATE_ACCEPTED,
                            "SMS accepted by the TextBee gateway (confirmed against its message "
                            "history after a connection error); carrier delivery is not confirmed.",
                            provider,
                        )
                    if known is None:
                        return (
                            SMS_STATE_UNKNOWN,
                            f"TextBee could not be reached and could not confirm the request "
                            f"({type(e).__name__}); nothing was resent, so a code may or may not "
                            "be on its way.",
                            provider,
                        )
                    if attempt <= extra_attempts:
                        _sleep_before_retry(attempt, None)
                        continue
                    return (
                        SMS_STATE_FAILED,
                        f"TextBee delivery failed: {type(e).__name__}; TextBee's history confirms "
                        "no message was queued.",
                        provider,
                    )

                try:
                    parsed = json.loads(body)
                except Exception:
                    parsed = None
                # An unreadable body on a 2xx is NOT acceptance (the old parser
                # treated it as success). Ask the provider, then decide.
                if not isinstance(parsed, dict):
                    known = _textbee_recent_send_exists(digits, request_started)
                    if known is True:
                        return (
                            SMS_STATE_ACCEPTED,
                            "SMS accepted by the TextBee gateway (confirmed against its message "
                            "history); carrier delivery is not confirmed.",
                            provider,
                        )
                    if known is None:
                        return (
                            SMS_STATE_UNKNOWN,
                            "TextBee returned an unreadable response and its message history was "
                            "not available; delivery is unconfirmed and nothing was resent.",
                            provider,
                        )
                    if attempt <= extra_attempts:
                        _sleep_before_retry(attempt, None)
                        continue
                    return (
                        SMS_STATE_FAILED,
                        "TextBee returned an unreadable response and its history confirms no "
                        "message was queued.",
                        provider,
                    )

                # TextBee wraps its body in a "data" object, so the older flat
                # `parsed.get("success")` test never matched a nested failure. A 200
                # here only means the request was ACCEPTED (queued for the Android
                # gateway); it is NOT evidence that the handset received anything.
                # Detect the documented rejection shapes explicitly instead.
                data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
                warning = data.get("warning") if isinstance(data.get("warning"), dict) else None
                accepted = data.get("success", parsed.get("success"))
                success_count = data.get("successCount") if "successCount" in data else parsed.get("successCount")
                failure_count = data.get("failureCount") if "failureCount" in data else parsed.get("failureCount")
                rejected = (
                    status >= 400
                    or bool(parsed.get("error"))
                    or accepted is False
                    or (
                        isinstance(success_count, int)
                        and isinstance(failure_count, int)
                        and failure_count > 0
                        and success_count == 0
                    )
                    or warning is not None
                )
                if rejected:
                    detail = (
                        (warning or {}).get("message")
                        or data.get("message")
                        or parsed.get("message")
                        or parsed.get("error")
                        or body[:200]
                    )
                    return (SMS_STATE_FAILED, f"TextBee rejected the request: {detail}", provider)
                return (
                    SMS_STATE_ACCEPTED,
                    "SMS accepted by the TextBee gateway; carrier delivery is not yet confirmed.",
                    provider,
                )

        if provider == "msg91":
            authkey = os.environ["SEEDIQ_MSG91_AUTHKEY"]
            template_id = (os.environ.get("SEEDIQ_MSG91_TEMPLATE_ID") or "").strip()
            if not template_id:
                return (SMS_STATE_FAILED, "SEEDIQ_MSG91_TEMPLATE_ID is not configured.", provider)
            var = (os.environ.get("SEEDIQ_MSG91_OTP_VAR") or "OTP").strip()
            payload = {
                "template_id": template_id,
                "short_url": "0",
                "recipients": [
                    {"mobiles": digits, var: otp, "OTP": otp, "VAR1": otp, "VAR2": "SeedIQ"}
                ],
            }
            sender = (os.environ.get("SEEDIQ_MSG91_SENDER") or "").strip()
            if sender:
                payload["sender"] = sender
            status, body = _post_json(
                "https://control.msg91.com/api/v5/flow/",
                payload,
                {"authkey": authkey, "Accept": "application/json"},
            )
            if status >= 400 or '"type":"error"' in body.replace(" ", ""):
                return (SMS_STATE_FAILED, f"MSG91 rejected the request: {body[:200]}", provider)
            return (
                SMS_STATE_ACCEPTED,
                "SMS accepted by MSG91; carrier delivery is not yet confirmed.",
                provider,
            )

        if provider == "twilio":
            sid = os.environ["TWILIO_ACCOUNT_SID"]
            token = os.environ["TWILIO_AUTH_TOKEN"]
            sender = (os.environ.get("TWILIO_FROM") or os.environ.get("TWILIO_PHONE_NUMBER") or "").strip()
            if not sender:
                return (SMS_STATE_FAILED, "TWILIO_FROM is not configured.", provider)
            import base64

            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
            messaging_service = (os.environ.get("TWILIO_MESSAGING_SERVICE_SID") or "").strip()
            fields = {"To": e164, "Body": message}
            if messaging_service:
                fields["MessagingServiceSid"] = messaging_service
            else:
                fields["From"] = sender
            status, body = _post_form(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                fields,
                {"Authorization": f"Basic {auth}", "Accept": "application/json"},
            )
            if status >= 400:
                return (SMS_STATE_FAILED, f"Twilio rejected the request: {body[:200]}", provider)
            return (
                SMS_STATE_ACCEPTED,
                "SMS accepted by Twilio; carrier delivery is not yet confirmed.",
                provider,
            )

        if provider == "fast2sms":
            key = os.environ["SEEDIQ_FAST2SMS_KEY"]
            status, body = _post_json(
                "https://www.fast2sms.com/dev/bulkV2",
                {"route": "q", "message": message, "numbers": digits},
                {"authorization": key, "Accept": "application/json"},
            )
            parsed = {}
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = {}
            if status >= 400 or parsed.get("return") is False:
                return (SMS_STATE_FAILED, f"Fast2SMS rejected the request: {body[:200]}", provider)
            return (
                SMS_STATE_ACCEPTED,
                "SMS accepted by Fast2SMS; carrier delivery is not yet confirmed.",
                provider,
            )

        if provider == "webhook":
            url = os.environ["SEEDIQ_SMS_WEBHOOK_URL"]
            headers = {"Accept": "application/json"}
            token = (os.environ.get("SEEDIQ_SMS_WEBHOOK_TOKEN") or "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            status, body = _post_json(
                url,
                {"phone": e164, "message": message, "otp": otp, "sender": "SeedIQ"},
                headers,
            )
            if status >= 400:
                return (SMS_STATE_FAILED, f"SMS webhook rejected the request: {body[:200]}", provider)
            return (
                SMS_STATE_ACCEPTED,
                "SMS accepted by the SMS webhook; carrier delivery is not yet confirmed.",
                provider,
            )
    except urllib.error.HTTPError as e:
        return (SMS_STATE_FAILED, f"{provider} delivery failed ({e.code}): {_http_error_detail(e)}", provider)
    except Exception as e:
        return (SMS_STATE_FAILED, f"{provider} delivery failed: {type(e).__name__} ({e})", provider)

    return (SMS_STATE_FAILED, f"Unsupported SMS provider '{provider}'.", provider)


def send_sms(digits: str, message: str, otp: str) -> tuple[bool, str, str | None]:
    """Back-compat wrapper over `send_sms_detailed`: (ok, human_message, provider).

    `ok=True` means the provider accepted the request or may have accepted it
    (UNKNOWN). It never means the handset or the carrier delivered the message.
    """
    state, text, provider = send_sms_detailed(digits, message, otp)
    return (state in (SMS_STATE_ACCEPTED, SMS_STATE_UNKNOWN), text, provider)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_phone_schema(conn) -> None:
    """Idempotent, additive migration — safe against an existing database."""
    try:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
    except Exception:
        pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS phone_otp (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'login',
            otp_hash TEXT NOT NULL,
            name TEXT DEFAULT '',
            attempts INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("ALTER TABLE phone_otp ADD COLUMN request_id TEXT")
    except Exception:
        pass
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone_unique
        ON users(phone) WHERE phone IS NOT NULL AND phone != '';
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_phone_otp_phone_purpose
        ON phone_otp(phone, purpose);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_phone_auth(
    app,
    get_db,
    log_activity,
    generate_password_hash,
    secret_key: str,
    test_mode: bool = False,
):
    """Attach the phone-authentication routes to `app`."""

    def _hash(phone: str, otp: str) -> str:
        return hmac.new(
            secret_key.encode(), f"{phone}:{otp}".encode(), hashlib.sha256
        ).hexdigest()

    def _now() -> datetime.datetime:
        return datetime.datetime.now()

    def _fmt(dt: datetime.datetime) -> str:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _cooldown() -> int:
        try:
            return max(0, int(os.environ.get("SEEDIQ_PHONE_OTP_COOLDOWN", "20")))
        except ValueError:
            return 20

    def _ttl() -> int:
        try:
            return max(60, int(os.environ.get("SEEDIQ_PHONE_OTP_TTL_SECONDS", "300")))
        except ValueError:
            return 300

    def _echo_enabled() -> bool:
        return os.environ.get("SEEDIQ_PHONE_OTP_ECHO", "").strip().lower() in ("1", "true", "yes")

    def _admin_phones() -> list[str]:
        raw = os.environ.get("SEEDIQ_ADMIN_PHONE", "919110252930")
        out = []
        for part in re.split(r"[,;\s]+", raw):
            if not part.strip():
                continue
            normalized = normalize_phone(part)
            if normalized:
                out.append(normalized)
        return out

    def _admin_phone_email() -> str:
        return os.environ.get("SEEDIQ_ADMIN_PHONE_EMAIL", "parnikaaa14@gmail.com").strip().lower()

    # ---------------------------------------------------------------- status
    @app.route("/api/auth/phone/status", methods=["GET"])
    def phone_auth_status():
        provider = active_sms_provider()
        payload = {
            "status": "success",
            "phone_auth": True,
            "otp_length": OTP_LENGTH,
            "otp_ttl_seconds": _ttl(),
            "cooldown_seconds": _cooldown(),
            "sms_provider": provider,
            "sms_ready": bool(provider),
            "sms_configured_providers": [
                name for name, ready in (
                    ("textbee", bool(_textbee_api_key())),
                    ("msg91", bool(os.environ.get("SEEDIQ_MSG91_AUTHKEY"))),
                    ("twilio", bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"))),
                    ("fast2sms", bool(os.environ.get("SEEDIQ_FAST2SMS_KEY"))),
                    ("webhook", bool(os.environ.get("SEEDIQ_SMS_WEBHOOK_URL"))),
                ) if ready
            ],
            "default_country_code": default_country_code(),
            "admin_phone_configured": bool(_admin_phones()),
        }
        if provider == "textbee":
            # Additive diagnostics only: the gateway phone's own view of its
            # health (heartbeat age, battery-optimization exemption). `sms_ready`
            # keeps its existing meaning ("a provider is configured").
            gw_ok, gw_reason, gw_detail = _textbee_gateway_preflight(ttl_seconds=60)
            payload["gateway_reachable"] = gw_ok
            payload["gateway"] = {
                "reason": gw_reason,
                # `gateway_reachable` answers "can we prove the phone is
                # receiving right now?"; this answers "would a send be refused?".
                "send_blocked": gw_ok is False and gw_reason in _TEXTBEE_BLOCKING_REASONS,
                **gw_detail,
            }
        return jsonify(payload), 200

    # ------------------------------------------------------------ request-otp
    @app.route("/api/auth/phone/request-otp", methods=["POST"])
    def phone_request_otp():
        data = request.get_json(silent=True) or {}
        raw_phone = data.get("phone") or data.get("mobile") or ""
        purpose = (data.get("purpose") or "login").strip().lower()
        if purpose not in ("login", "register"):
            purpose = "login"

        digits = normalize_phone(raw_phone, data.get("country_code"))
        if not digits:
            return jsonify({
                "status": "error",
                "code": "invalid_phone",
                "message": "Enter a valid mobile number (10 digits for India).",
            }), 400

        provider = active_sms_provider()
        if not provider and not _echo_enabled():
            return jsonify({
                "status": "error",
                "code": "sms_provider_not_configured",
                "message": (
                    "Phone verification is unavailable: the server has no SMS provider configured. "
                    "Set SEEDIQ_TEXTBEE_API_KEY (TextBee Android gateway) in the backend environment."
                ),
            }), 503

        # Refuse only on concrete evidence that the phone cannot take the
        # message (no/disabled device, or a recent push it never acknowledged).
        # TextBee accepts sends for a merely quiet gateway - the message waits
        # until the phone comes back - so heartbeat age alone must not block
        # sign-in. The 503 keeps its existing shape (status/code/message plus the
        # additive `gateway` detail block the app already renders as a provider
        # error).
        if provider == "textbee" and not _echo_enabled() and not test_mode:
            gw_ok, gw_reason, gw_detail = _textbee_gateway_preflight()
            if gw_ok is False and gw_reason in _TEXTBEE_BLOCKING_REASONS:
                block_code, block_message = _TEXTBEE_BLOCK_RESPONSES[gw_reason]
                log_activity(
                    "PHONE_OTP_GATEWAY_UNAVAILABLE", user_id=None,
                    details={"phone": masked_phone(digits), "reason": gw_reason, **gw_detail},
                    status="FAILED",
                )
                return jsonify({
                    "status": "error",
                    "code": block_code,
                    "message": block_message,
                    "gateway": {"reason": gw_reason, **gw_detail},
                }), 503

        now = _now()
        with get_db() as conn:
            ensure_phone_schema(conn)
            existing = conn.execute(
                "SELECT * FROM phone_otp WHERE phone = ? AND purpose = ?", (digits, purpose)
            ).fetchone()

            if not test_mode and existing and existing["created_at"]:
                try:
                    created = datetime.datetime.strptime(existing["created_at"], "%Y-%m-%d %H:%M:%S")
                    elapsed = (now - created).total_seconds()
                    if elapsed < _cooldown():
                        remaining = int(_cooldown() - elapsed) + 1
                        return jsonify({
                            "status": "error",
                            "code": "cooldown",
                            "retry_after": remaining,
                            "message": f"Please wait {remaining} seconds before requesting another code.",
                        }), 429
                except Exception:
                    pass

            request_id = secrets.token_hex(16)
            otp = str(secrets.randbelow(OTP_SPAN) + OTP_MIN)
            expires_at = _fmt(now + datetime.timedelta(seconds=_ttl()))
            conn.execute("DELETE FROM phone_otp WHERE phone = ? AND purpose = ?", (digits, purpose))
            conn.execute(
                "INSERT INTO phone_otp (phone, purpose, otp_hash, name, attempts, created_at, expires_at, request_id)"
                " VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
                (digits, purpose, _hash(digits, otp), (data.get("name") or "").strip()[:80], _fmt(now), expires_at, request_id),
            )
            conn.commit()

        log_activity("PHONE_OTP_SENT", user_id=None, details={"phone": masked_phone(digits), "purpose": purpose})

        message = (
            f"{otp} is your SeedIQ verification code. It expires in "
            f"{_ttl() // 60} minutes. Do not share it with anyone."
        )
        ok, status_msg, used_provider = send_sms(digits, message, otp)

        if not ok and not _echo_enabled():
            # Never leave a live code behind when delivery failed: the user would
            # be locked out by the cooldown otherwise.
            with get_db() as conn:
                conn.execute("DELETE FROM phone_otp WHERE phone = ? AND purpose = ?", (digits, purpose))
                conn.commit()
            log_activity(
                "PHONE_OTP_FAILED", user_id=None,
                details={"phone": masked_phone(digits), "provider": used_provider}, status="FAILED",
            )
            return jsonify({
                "status": "error",
                "code": "sms_delivery_failed",
                "message": status_msg,
                "provider": used_provider,
            }), 502

        # `ok` from send_sms means the provider *accepted* the request. It is not
        # proof of handset delivery (TextBee queues to the Android gateway and
        # returns 200 before the phone has sent anything), so the wording says
        # "submitted" rather than claiming the code was delivered. The existing
        # response keys are unchanged; `delivery` is additive.
        payload = {
            "status": "success",
            "request_id": request_id,
            "message": (
                f"Verification code submitted to the SMS gateway for "
                f"{pretty_phone(digits)}. Delivery is not confirmed until it arrives."
            ),
            "phone": pretty_phone(digits),
            "otp_length": OTP_LENGTH,
            "expires_in": _ttl(),
            "provider": used_provider,
            "delivery": "accepted",
        }
        if _echo_enabled():
            # Explicitly opt-in, for local testing only.
            payload["message"] = f"Local test mode: your code is {otp}."
            payload["debug_code"] = otp
        return jsonify(payload), 200

    @app.route("/api/auth/phone/resend", methods=["POST"])
    def phone_resend_otp():
        return phone_request_otp()

    # ------------------------------------------------------------- verify-otp
    @app.route("/api/auth/phone/verify-otp", methods=["POST"])
    def phone_verify_otp():
        data = request.get_json(silent=True) or {}
        req_id = data.get("request_id")
        digits = normalize_phone(data.get("phone") or data.get("mobile"), data.get("country_code"))
        code = re.sub(r"\D", "", str(data.get("otp") or data.get("code") or ""))

        if not digits:
            return jsonify({"status": "error", "code": "invalid_phone",
                            "message": "Enter a valid mobile number."}), 400
        if len(code) != OTP_LENGTH:
            return jsonify({"status": "error", "code": "invalid_code_format",
                            "message": f"Enter the {OTP_LENGTH}-digit verification code."}), 400

        with get_db() as conn:
            ensure_phone_schema(conn)
            record = conn.execute(
                "SELECT * FROM phone_otp WHERE phone = ? ORDER BY id DESC LIMIT 1", (digits,)
            ).fetchone()
            if not record:
                return jsonify({"status": "error", "code": "no_pending_code",
                                "message": "No pending code for this number. Request a new one."}), 400

            if req_id and "request_id" in record.keys() and record["request_id"] and record["request_id"] != req_id:
                return jsonify({"status": "error", "code": "invalid_request_id",
                                "message": "Invalid verification session. Request a new code."}), 400

            attempts = record["attempts"] or 0
            if attempts >= MAX_ATTEMPTS:
                conn.execute("DELETE FROM phone_otp WHERE phone = ?", (digits,))
                conn.commit()
                return jsonify({"status": "error", "code": "too_many_attempts",
                                "message": "Too many attempts. Please request a new code."}), 429

            # Expiry is checked before the hash so an expired code tells the user
            # what to do next instead of burning one of their attempts.
            if record["expires_at"] < _fmt(_now()):
                conn.execute("DELETE FROM phone_otp WHERE phone = ?", (digits,))
                conn.commit()
                return jsonify({"status": "error", "code": "expired",
                                "message": "That code has expired. Please request a new one."}), 400

            if not hmac.compare_digest(str(record["otp_hash"]), _hash(digits, code)):
                conn.execute("UPDATE phone_otp SET attempts = attempts + 1 WHERE id = ?", (record["id"],))
                conn.commit()
                remaining = MAX_ATTEMPTS - (attempts + 1)
                return jsonify({
                    "status": "error",
                    "code": "incorrect_code",
                    "attempts_remaining": max(0, remaining),
                    "message": f"Incorrect code. {max(0, remaining)} attempt(s) left.",
                }), 401

            conn.execute("DELETE FROM phone_otp WHERE phone = ?", (digits,))
            conn.commit()

            is_admin_phone = digits in _admin_phones()
            admin_email = _admin_phone_email()

            user = conn.execute("SELECT * FROM users WHERE phone = ?", (digits,)).fetchone()
            created = False

            if not user and is_admin_phone:
                # Bind the client's admin number to the client's admin mailbox.
                user = conn.execute("SELECT * FROM users WHERE email = ?", (admin_email,)).fetchone()

            if not user:
                username = digits
                email = admin_email if is_admin_phone else synthetic_email(digits)
                role = "Admin" if is_admin_phone else "Farmer"
                display = (data.get("name") or record["name"] or "").strip()
                if not display:
                    display = "SeedIQ Administrator" if is_admin_phone else pretty_phone(digits)
                try:
                    conn.execute(
                        "INSERT INTO users (username, password, email, display_name, role, provider, phone)"
                        " VALUES (?, ?, ?, ?, ?, 'phone', ?)",
                        (username, generate_password_hash(secrets.token_urlsafe(32)),
                         email, display[:80], role, digits),
                    )
                    conn.commit()
                except Exception:
                    # Username or e-mail already taken: fall back to a suffixed username.
                    conn.execute(
                        "INSERT INTO users (username, password, email, display_name, role, provider, phone)"
                        " VALUES (?, ?, ?, ?, ?, 'phone', ?)",
                        (f"{digits}_{secrets.randbelow(900) + 100}",
                         generate_password_hash(secrets.token_urlsafe(32)),
                         synthetic_email(digits), display[:80], role, digits),
                    )
                    conn.commit()
                user = conn.execute("SELECT * FROM users WHERE phone = ?", (digits,)).fetchone()
                created = True
            else:
                # Existing account: keep the phone bound and honour the admin role.
                updates = "phone = ?"
                params = [digits]
                if is_admin_phone:
                    updates += ", role = 'Admin'"
                    if not user["email"] or user["email"] != admin_email:
                        try:
                            conn.execute("UPDATE users SET email = ? WHERE id = ?", (admin_email, user["id"]))
                        except Exception:
                            pass
                conn.execute(f"UPDATE users SET {updates} WHERE id = ?", (*params, user["id"]))
                conn.commit()
                user = conn.execute("SELECT * FROM users WHERE phone = ?", (digits,)).fetchone()

        role = (user["role"] or "Farmer") if user else "Farmer"
        if user and user["email"] and user["email"].lower() == _admin_phone_email():
            role = "Admin"

        session.clear()
        session["user_id"] = user["id"]
        session["sqlite_user_id"] = user["id"]
        session["username"] = user["username"]
        session["email"] = user["email"]
        session["phone"] = digits
        session["role"] = role
        session["display_name"] = user["display_name"] or user["username"]
        session["is_guest"] = False
        session["auth_provider"] = "phone_otp"

        log_activity(
            "USER_REGISTERED" if created else "USER_LOGIN",
            user_id=str(user["id"]),
            details={"phone": masked_phone(digits), "provider": "phone_otp", "role": role},
        )
        log_activity("PHONE_OTP_VERIFIED", user_id=str(user["id"]), details={"phone": masked_phone(digits)})

        return jsonify({
            "status": "success",
            "created": created,
            "message": "Account created successfully." if created else "Signed in successfully.",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "phone": digits,
                "display_name": user["display_name"] or user["username"],
                "role": role,
                "provider": "phone_otp",
            },
        }), (201 if created else 200)

    return app


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def ensure_phone_admin_account(get_db, generate_password_hash) -> str | None:
    """
    Make sure the client's admin phone number maps to the client's admin mailbox
    with the Admin role. The account is password-less by design (OTP only), so a
    random unusable hash is stored and no secret ever reaches the mobile app.
    """
    raw = os.environ.get("SEEDIQ_ADMIN_PHONE", "919110252930")
    email = os.environ.get("SEEDIQ_ADMIN_PHONE_EMAIL", "parnikaaa14@gmail.com").strip().lower()
    digits = None
    for part in re.split(r"[,;\s]+", raw):
        if part.strip():
            digits = normalize_phone(part)
            if digits:
                break
    if not digits:
        return None

    try:
        with get_db() as conn:
            ensure_phone_schema(conn)
            row = conn.execute("SELECT * FROM users WHERE phone = ?", (digits,)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET phone = ?, role = 'Admin', provider = 'phone',"
                    " display_name = COALESCE(NULLIF(display_name, ''), 'SeedIQ Administrator')"
                    " WHERE id = ?",
                    (digits, row["id"]),
                )
            else:
                # OR IGNORE: worker processes boot in parallel and can both reach
                # this branch, which is a plain UNIQUE failure for the loser.
                conn.execute(
                    "INSERT OR IGNORE INTO users (username, password, email, display_name, role, provider, phone)"
                    " VALUES (?, ?, ?, 'SeedIQ Administrator', 'Admin', 'phone', ?)",
                    (digits, generate_password_hash(secrets.token_urlsafe(32)), email, digits),
                )
            conn.commit()
        return digits
    except Exception as e:
        print(f"[PHONE_AUTH] Admin phone bootstrap notice: {e}")
        return None
