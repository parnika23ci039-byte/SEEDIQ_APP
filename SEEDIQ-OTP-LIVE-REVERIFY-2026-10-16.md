# SeedIQ SMS OTP — live test, diagnosis, fix, deploy, verification (2026-10-16, 03:4x–04:1x IST)

Scope respected: only OTP files were touched — `SeedIQ/phone_auth.py` and its guard test
`experiments/client_model_audit/test_textbee_gateway_guard.py`. No AI/crop features, UI,
navigation, language settings or other login paths were modified; every pre-existing
uncommitted change and local artifact was left in place. Nothing was committed or pushed.
No API key, session token, OTP value or full phone number appears in this report or in any
tool output: numbers are shown masked (`+91*****2930`, `+91*****5336`), and the probe script
prints only a whitelist of fields.

## 1. Confirmed root cause

**The TextBee Android gateway phone stopped consuming messages, and the API kept answering
"succeeded".**

The gateway device (`realme RMX3870`, enabled, default) last reported at **10-15 23:19:40 IST**;
by the time of testing its heartbeat was **263–285 minutes stale** with
`battery_optimization_exempt: false`. TextBee's own record showed messages it had accepted and
the phone had **never acknowledged** (`pushReceivedAt=-`, "Status update timeout - no response
from device after dispatch") — three of them: 10-15 22:25, 10-16 01:44, and the controlled
request at 03:47. So no SMS could be sent, by anyone, until the phone returns.

Layered on top was a real software defect, confirmed live:

- `_TEXTBEE_BLOCKING_REASONS` deliberately excludes heartbeat staleness (a quiet gateway can
  still accept sends; blocking on heartbeat age alone had taken sign-in down on 10-15) — fine.
- The evidence that *does* block, an accepted-but-unacknowledged message, was only considered
  when the message was **inside `SEEDIQ_TEXTBEE_PREFLIGHT_WINDOW_SECONDS` (3600 s)**. During an
  outage longer than an hour, every stuck message is by definition older than that window, so
  the check could never fire — exactly when it matters.
- Result, measured: the controlled request at **03:47:41 IST returned `200 {"status":"success",
  "delivery":"accepted"}`**, TextBee queued the message, and the 300 s code could only ever
  arrive expired. The app showed "code submitted / not confirmed" and the user waited forever.

**Ruled out with live evidence:** wrong/outdated API URL (the app's Railway URL answers and the
new gateway fields are present), wrong endpoint or body (probe used the app's exact
`{phone, purpose:"login"}` to `/api/auth/phone/request-otp`), missing/misparsed TextBee config
(`sms_provider: textbee`, `sms_ready: true`, `sms_configured_providers: ["textbee"]`, real device
data returned), deployed-code drift (the running `phone_auth.py` matched the file the tests ran
against, hash `1b1bbdc5…`), and the client's error mapping (already fixed and deployed earlier:
the 503 code `sms_gateway_unavailable` renders as the true, actionable message in en/hi/kn).

## 2. Exact OTP files changed

| File | Change |
| --- | --- |
| `SeedIQ/phone_auth.py` | `_textbee_gateway_preflight`: the unacknowledged-message scan now also records the same evidence **without** the 1 h window, and refuses (`gateway_not_receiving`) when a **stale heartbeat** and a **never-acknowledged message of any age** both hold. Two doc blocks updated so the rule is not "fixed" back. No OTP generation, expiry, cooldown, attempt limit, verification, retry or provider code touched. |
| `experiments/client_model_audit/test_textbee_gateway_guard.py` | New section 4b: 8 checks pinning the long-outage case (live scenario → 503 `sms_gateway_unavailable`, no code stored, no SMS dispatched, masked recipient only, `send_blocked: true`), self-healing when the phone drains the backlog, and the signal discipline (neither signal blocks alone; inside-grace is not evidence). |

Not changed: `seediq-mobile/**` (no client defect exists for this failure — the 503 is already
mapped correctly), the APK (no rebuild needed), the provider adapters, and every non-OTP module.

## 3. Live status response and the requests (sanitized)

`GET /api/auth/phone/status` — before the fix (03:43 IST):

```json
{"sms_provider":"textbee","sms_ready":true,"gateway_reachable":false,
 "gateway":{"reason":"heartbeat_stale","send_blocked":false,"heartbeat_enabled":true,
            "last_heartbeat_age_minutes":260.9,"battery_optimization_exempt":false,
            "doze_mode":false,"device_id":"6ac25f4536a1b2304e5aa8d7"}}
```

Controlled request #1 — **03:47:41 IST**, app's real format, authorized admin/test handset:

```
POST /api/auth/phone/request-otp   ->   HTTP 200   (4.12 s)
{"status":"success","delivery":"accepted","provider":"textbee","expires_in":300,"otp_length":4}
message: "Verification code submitted to the SMS gateway for <number>. Delivery is not confirmed until it arrives."
```

`GET /api/auth/phone/status` — after the fix (04:0x IST):

```json
{"sms_provider":"textbee","sms_ready":true,"gateway_reachable":false,
 "gateway":{"reason":"gateway_not_receiving","send_blocked":true,
            "last_heartbeat_age_minutes":283.2,"unacknowledged_age_seconds":912.4,
            "unacknowledged_to":"+91*****2930","battery_optimization_exempt":false,
            "doze_mode":false,"device_id":"6ac25f4536a1b2304e5aa8d7"}}
```

Controlled request #2 — **after the deploy**, same format. This one **cannot** send: with
`send_blocked: true` the guard refuses before any code is generated, and TextBee's message total
was verified unchanged (40 → 40), so provably nothing was queued:

```
POST /api/auth/phone/request-otp   ->   HTTP 503   (2.59 s)
{"status":"error","code":"sms_gateway_unavailable",
 "message":"The SMS gateway phone is not reachable right now, so no code was sent and nothing was queued. Please try again in a few minutes.",
 "gateway":{"reason":"gateway_not_receiving","last_heartbeat_age_minutes":285.3,
            "unacknowledged_age_seconds":1035.4,"unacknowledged_to":"+91*****2930", ...}}
```

No `delivery` and no `request_id` in the refusal — nothing was generated, and no cooldown was burned.

## 4. Test commands and exact results

| Command | Result | Exit |
| --- | --- | --- |
| `.freebuff/venv/bin/python3 experiments/client_model_audit/test_phone_otp_isolated.py` | 28/28 | 0 |
| `.freebuff/venv/bin/python3 experiments/client_model_audit/test_textbee_response_handling.py` | 11/11 | 0 |
| `.freebuff/venv/bin/python3 experiments/client_model_audit/test_textbee_gateway_guard.py` | **37/37** (was 29) | 0 |
| `.freebuff/venv/bin/python3 experiments/client_model_audit/test_textbee_retry_policy.py` | 32/32 | 0 |
| same guard suite against an **emulated pre-fix** module (`/tmp/seediq-prefix`) | **31/37** — the 6 new long-outage checks fail, incl. `HTTP 200` and `codes=1 sends=1` | 1 |
| `python3 -m py_compile` on both edited files | clean | 0 |
| staged-tree check: `import app`, four `/api/auth/phone/*` routes register, `/status` shape OK | pass | 0 |

The pre-fix run is the important one: it reproduces the defect in a test — the same scenario
that now returns 503 with nothing generated returned **200 and actually generated and dispatched
a code**. Assertions were added, never weakened or skipped.

## 5. Railway deployment

| Item | Value |
| --- | --- |
| Project / environment / service | SeedIQ Backend `634e9703-7a24-4f87-a299-da2b58261c10` / production `74170432-2f3a-44b2-862c-03726e67fb65` / sublime-ambition `3bb53fa2-9171-4b97-bab2-c2cc6b508902` |
| Deployment | **`d0687a7f-11b9-4b23-80ac-a0a2e0ffc37e` → SUCCESS** (2026-10-16 04:00:28 IST) |
| Previous deployment | `9b4d90e8-…` → REMOVED |
| Startup log | `Starting Container` → `[bootstrap] expanded SeedIQ-runtime.tar.xz` → gunicorn 26.2.0 on 0.0.0.0:8080, 2 workers, `[PHONE_AUTH] Admin phone account ready: +91*****2930`, no tracebacks |
| Uploaded archive | SHA-256 `1a4d8da4…`; **203 entries in the identical order** as the previous archive; recursive tree diff = exactly one changed file (`SeedIQ/phone_auth.py`); archived copy byte-identical to the repo file (SHA-256 `7123d9f4e804daea026172b31ae9affc02b0089b210417c1dfa0a6df281ef654`); no secret material in the archive |
| Pre-deploy backup | `~/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-v4-predeploy` |

Rollback (one command, previous archive restored and re-uploaded):

```sh
cp ~/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-v4-predeploy \
   ~/seediq-prod-deploy/SeedIQ-runtime.tar.xz
cd ~/seediq-prod-deploy && railway up --ci -y \
  -s 3bb53fa2-9171-4b97-bab2-c2cc6b508902 -e 74170432-2f3a-44b2-862c-03726e67fb65
```

## 6. TextBee acknowledgement status

- **Accepted:** yes. Every request TextBee received was queued (`dispatched`/`unknown`), including
  the 03:47 controlled request, and the provider incremented its message total to 40.
- **Acknowledged by the gateway phone:** **no.** For all three stuck messages
  `pushReceivedAt`, `attemptedAt`, `sentAt` and `deliveredAt` are all absent, with the provider's
  own error `Status update timeout - no response from device after dispatch`. The phone has not
  reported since 10-15 23:19:40 IST and is not battery-optimization exempt.
- **After the fix:** the refused request produced **no new message at all** (total 40 → 40),
  which is the proof that the 503 is a real refusal and not a queued "success".

## 7. Was the SMS actually received on the handset?

**NO.** No SMS was sent by the gateway for any of the three stuck messages, and the controlled
request before the fix did not change that. The 03:47 message is still `dispatched` with no push;
the code it carried expired 300 s later. Delivery cannot happen while the gateway phone is asleep,
and no code change can change that.

## 8. What remains blocked, and the client action needed

**Nothing software-side is blocking OTP now — the remaining blocker is the phone.** Owner action
(≈2 minutes, no deploy, no code change):

1. Charge/unlock the gateway phone (`realme RMX3870`) and open the TextBee app.
2. Android Settings → Apps → TextBee → Battery → **Unrestricted** (this is what flips
   `battery_optimization_exempt` to `true`; it is `false` today, and the app is being frozen).
3. Confirm recovery: `GET /api/auth/phone/status` shows `gateway_reachable: true`,
   `send_blocked: false`, and the three stuck messages acquire `pushReceivedAt`.
4. Then request one OTP from the app; the code is 4 digits with a 300 s TTL.

The block **clears by itself** — the moment the phone takes the backlog or heartbeats again, the
preflight stops refusing and sends resume, with no deploy and no manual reset. No fallback
provider is configured (`sms_configured_providers: ["textbee"]`; the MSG91/Twilio/Fast2SMS/webhook
adapters exist in code but have no credentials, and none were invented).

### Pending verification (scheduled, read-only)

The deploy happened while the newest stuck message was still inside the 1 h window, so at that
instant both the old and new rule refuse and the observation cannot tell them apart. A background
job (`/tmp/seediq_window_discriminator.sh`, PID 83908, verdict file
`/tmp/seediq_after_window_verdict.txt`, JSON `/tmp/seediq_after_window.json`) waits until that
message is past the window and re-reads `/status`: the fixed build must still report
`gateway_not_receiving` with `unacknowledged_age_seconds > 3600`, where the pre-fix build would
have reported `heartbeat_stale` / `send_blocked: false`.

### What was not done

- No APK rebuild (no confirmed client-side defect for this failure) and no client file changed.
- No second SMS was attempted: the post-fix request provably queued nothing.
- Nothing was committed or pushed; all edits remain uncommitted in the working tree.
