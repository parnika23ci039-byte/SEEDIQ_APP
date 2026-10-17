# SeedIQ P0 — TextBee OTP emergency fix, 2026-10-16

**Scope respected:** only `SeedIQ/phone_auth.py` (OTP-only policy) and
`experiments/client_model_audit/test_textbee_gateway_guard.py` were touched. No UI,
models, navigation, language selector, or non-phone-OTP auth was modified. No
production secret or environment variable was read or changed. All pre-existing
uncommitted work is untouched.

## 1. Exact root cause — two layers

**Layer A (the code cause of the client's exact error).** The gateway preflight added
on 10-15 hard-refused a send whenever the last heartbeat was older than
`max(45 min, 2 × heartbeatIntervalMinutes)`. TextBee documents the opposite:
"**The API still accepts sends for it, and the messages wait until the phone comes
back**" ([messages-not-sending](https://textbee.dev/docs/troubleshooting/messages-not-sending)),
and its device guide treats `lastHeartbeat` as a health indicator, not an
online/offline switch ([devices](https://textbee.dev/docs/devices)). So heartbeat age
alone was stricter than the provider's actual behaviour, and it took sign-in down:

```
2026-10-15T19:43:39Z  POST /api/auth/phone/request-otp 503 526ms   <- client attempt
2026-10-15T19:43:49Z  POST /api/auth/phone/request-otp 503 618ms   <- client attempt
reason=heartbeat_stale  last_heartbeat_age_minutes=120.5
device enabled=true isDefault=true doze_mode=false
```
Both client attempts were refused solely on heartbeat age — while the device was
enabled, default, and not in Doze. The app renders any 503 as "SMS service is
unavailable or not configured on the server. Retry."

**Layer B (the underlying gateway condition).** The gateway phone stopped
heartbeating at ~23:18 IST on 10-15 (age 147 min by 01:44 IST) and is not taking
pushes — proven below by the provider's own record, not assumed.

**Ruled out, with evidence:** credentials/config (TextBee answered device and message
queries throughout; `sms_provider: textbee`, `sms_ready: true`), API misuse (the
documented request shape is used and was accepted), and deployment mismatch (the
previous deployment was confirmed live and serving the new status fields).

## 2. OTP-specific files changed

| File | Change |
| --- | --- |
| `SeedIQ/phone_auth.py` | `_textbee_gateway_preflight` now evaluates the provider's message backlog first and reports heartbeat staleness without gating on it; new `_TEXTBEE_BLOCKING_REASONS = {no_enabled_device, device_disabled, gateway_not_receiving}`; `/request-otp` refuses only for those reasons; `/status` gains additive `gateway.send_blocked`; policy comment rewritten with the documented rationale |
| `experiments/client_model_audit/test_textbee_gateway_guard.py` | Expectations corrected to the documented policy (stale heartbeat alone → 200 and a real dispatch; evidence → refusal), plus new status-contract checks |

Deployed `phone_auth.py` SHA-256:
`21016a2772601f1801c4405a2bdf765f8e9dbb7ea3dfc3c9d16c9cf5d1aa0cf5` (identical in the
repo and inside the deployed archive).

## 3. Tests — counts and exit statuses

| Suite | Result | Exit |
| --- | --- | --- |
| `test_phone_otp_isolated.py` | 28/28 | 0 |
| `test_textbee_response_handling.py` | 11/11 | 0 |
| `test_textbee_gateway_guard.py` | 26/26 (was 23; +3 policy checks) | 0 |
| `test_textbee_retry_policy.py` | 32/32 | 0 |

Aggregate exit 0; `py_compile` clean. Assertions were corrected where the requested
behaviour changed — never weakened to pass. New assertions that now fail if the gate
regresses:

```
[PASS] stale heartbeat alone -> HTTP 200
[PASS] code stored and a send attempted — codes=1 sends=1
[PASS] response still does NOT claim delivery — accepted
[PASS] status reports the stale heartbeat honestly — reachable=False reason=heartbeat_stale
[PASS] status distinguishes 'not proven reachable' from 'send refused' — send_blocked=False
[PASS] heartbeat age is still surfaced for support — 180.0
[PASS] unacknowledged message 5 min old -> HTTP 503 (evidence beats a quiet heartbeat)
[PASS] status marks this gateway as send_blocked
[PASS] refused attempt does not burn the cooldown (retry after recovery -> 200)
```

## 4. Railway deployment

- Deployment `ff82fdf8-36f2-4bd2-88f4-2487d046c559` → **SUCCESS** (2026-10-16 01:40:15 IST),
  previous `39e2124b-…` REMOVED. Same service/project/environment as before
  (`SeedIQ Backend` / `production` / `sublime-ambition`, sfo).
- New archive SHA-256 `1770e20dfb95cffcc4662a25a9e67a4d64fb4d564845e43a6b4df2fbf829e65a`;
  entry list identical to the previous production archive (203 entries) and a
  recursive diff shows **exactly one changed file: `phone_auth.py`**.
- Rollback point: `/Users/apple/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-v2-predeploy`
  (the pre-OTP-fix archive from Oct 9 is also still kept).

## 5. Live behaviour after deploy

```
GET  /api/auth/phone/status                200  1630ms
     reason=heartbeat_stale  send_blocked=false  gateway_reachable=false  heartbeat_age=143.8 min
POST /api/auth/phone/request-otp           200  3663ms  (was 503 before the deploy)
     {"delivery":"accepted","message":"Verification code submitted to the SMS gateway for
      +91 … Delivery is not confirmed until it arrives.","provider":"textbee"}
```

Then, after the 90 s acknowledgement grace, the provider's own record decided:

```
GET /api/auth/phone/status
     reason=gateway_not_receiving   send_blocked=true
     unacknowledged_age_seconds=184.3   unacknowledged_to=+91*****2930
```

One live request only (no repeated sends), to the owner-authorized admin handset. That
message is still queued at TextBee and may arrive late on that handset; its code
expired 300 s after 20:14 UTC.

## 6. Does real SMS delivery work with the TextBee phone offline?

**No — proven, not assumed.** The API accepted the send (200, `delivery: accepted`),
and the phone never acknowledged it, which is exactly the documented offline-queue
behaviour. TextBee has **no cloud SMS relay**: the Android phone sends every message
("Does my phone need to stay on? — Yes",
[README](https://github.com/textbee/textbee/blob/main/README.md)), and a paused app
holds messages "sometimes for minutes or hours"
([keep-the-phone-online](https://textbee.dev/docs/troubleshooting/keep-the-phone-online)).
No server-side code can overcome that; a `200` is acceptance, never delivery.

**No fallback provider is available tonight.** `sms_configured_providers` reports
`["textbee"]` only — MSG91/Twilio/Fast2SMS/webhook adapters exist in the code but none
is configured, and the client cannot register a new service now. Nothing was invented
or silently switched.

## 7. Unavoidable external dependency + owner action

**Wake the gateway phone (about 2 minutes, no deploy needed):** charge/unlock it, open
the TextBee app, keep it in the foreground briefly, and set Android → Apps → TextBee →
Battery → **Unrestricted**. As soon as the phone takes the queued push or sends a
heartbeat, `GET /api/auth/phone/status` flips to `gateway_reachable: true` and
`send_blocked: false` **automatically** — the guard is self-clearing and needs no
redeploy or env change.

If the phone cannot be woken tonight, the gateway-independent options (both need the
owner, not code):

1. Register a second Android phone in TextBee and set it as the default device —
   same vendor, no new account.
2. Configure one of the adapters already in the code (MSG91, Twilio, Fast2SMS, or
   `SEEDIQ_SMS_WEBHOOK_URL`); the send path already supports them and only the
   credentials are missing.

Tuning knob if the 1-hour evidence window is too long/short:
`SEEDIQ_TEXTBEE_PREFLIGHT_WINDOW_SECONDS` (default 3600) and
`SEEDIQ_TEXTBEE_PREFLIGHT_GRACE_SECONDS` (default 90).

## 8. Security — what was deliberately not done

No manual `gateway_reachable = true`, no disabled verification, no hardcoded or logged
OTP, no success response without provider acceptance, no indefinite queueing claimed as
delivery, and no removal of expiry, cooldown or rate-limiting. Responses still say
"submitted… Delivery is not confirmed until it arrives."

**Android:** no rebuild. The client's error text for a 503 remains accurate and
localised, and no mobile change was proven necessary, so the delivered
[deliverables/SeedIQ-Android-v1.2.3-release.apk](deliverables/SeedIQ-Android-v1.2.3-release.apk)
(95,224,045 B, SHA-256 `b13590ce…`) is untouched.
