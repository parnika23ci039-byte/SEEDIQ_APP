# SeedIQ OTP backend deploy + live verification — 2026-10-16

**Status: the OTP fix is DEPLOYED and PROVEN LIVE on production. Real SMS receipt is
still unverified because the gateway phone itself is offline to TextBee.**

## What was deployed

| Item | Value |
| --- | --- |
| Railway workspace | parnikaaa14's Projects |
| Project | SeedIQ Backend (`634e9703-7a24-4f87-a299-da2b58261c10`) |
| Environment | production (`74170432-2f3a-44b2-862c-03726e67fb65`) |
| Service | sublime-ambition (`3bb53fa2-9171-4b97-bab2-c2cc6b508902`), sfo |
| URL | https://sublime-ambition-production-488f.up.railway.app |
| Deployment | `39e2124b-b5b8-4db3-a3d2-efab7479633c` → **SUCCESS** (2026-10-16 00:36:55 IST) |
| Previous running deployment | `d2e921d2-…` (2026-10-09, old unguarded send path) → REMOVED |
| Previous failed attempt | `e32fc8e0-…` (2026-10-13) → FAILED, root cause: upload context was the repo root, so railpack could not open `SeedIQ/requirements.txt` |

Deploy pipeline (unchanged from the known-good Oct 9 recipe):
`~/seediq-prod-deploy` (5 small files) → Procfile `web: sh start.sh` → `start.sh`
expands `SeedIQ-runtime.tar.xz` and execs
`gunicorn --chdir SeedIQ app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120`.

- New archive SHA-256: `69e7129bd7de7655f481bdc0ef2efb16d07bbd964e3b7e0e1f1344e7825b8ac2`
- Deployed `phone_auth.py` SHA-256: `daa6d631a0a56b394d382a62259a2cd912899b6f07422228b762e151f8425534`
  — bit-identical to `SeedIQ/phone_auth.py` and to the file the four test suites ran against.
- Archive entry list is byte-for-byte the same 203 entries as the previous production
  archive; a recursive diff of the two extracted trees shows **exactly one changed file:
  `SeedIQ/phone_auth.py`**. Nothing else in the runtime changed.
- No secrets in the archive (checked for `.env`, keys, keystores, PEMs: none).
- Pre-deploy backup of the previous archive:
  `/Users/apple/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-predeploy`

Local pre-deploy proof (no network, no SMS): in the exact staged tree with the fixed
module, `import app` succeeds, all four phone routes register
(`/status`, `/request-otp`, `/resend`, `/verify-otp`), and `/api/auth/phone/status`
answered 200 with the new `gateway_reachable` + `gateway` fields.

Production startup log (new deployment):
`[bootstrap] expanded SeedIQ-runtime.tar.xz` → gunicorn 26.2.0 on 0.0.0.0:8080,
2 workers, `[PHONE_AUTH] Admin phone account ready: +91*****2930`, no tracebacks.

## Live verification

`GET /api/auth/phone/status` now returns the gateway-health block (it did not exist
before this deploy — the field itself proves the new code is the code that is running):

```json
{"gateway": {"battery_optimization_exempt": false, "device_id": "6ac25f4536a1b2304e5aa8d7",
 "doze_mode": false, "heartbeat_enabled": true, "last_heartbeat_age_minutes": 104.4,
 "reason": "heartbeat_stale"}, "gateway_reachable": false, ...}
```

Controlled live test — **one** POST to the configured admin handset
(`+91*****2930`), authorized by the owner:

```
POST /api/auth/phone/request-otp   http=503   total_time=1.445s
{"code":"sms_gateway_unavailable",
 "message":"The SMS gateway phone is not reachable right now, so no code was sent and
            nothing was queued. Please try again in a few minutes.",
 "gateway":{"reason":"heartbeat_stale","last_heartbeat_age_minutes":104.4, ...},
 "status":"error"}
```

Server-side HTTP log: `POST /api/auth/phone/request-otp 503 839ms`.

Post-check `/status`: unchanged (`gateway_reachable: false`, same heartbeat age) —
nothing was queued, no cooldown burned, no SMS sent. Before this deploy the same
call returned `200 {"status":"success"}` and the code sat queued until the phone
woke up, which is exactly the multi-hour delay the client reported.

## Root cause (now visible in production)

The TextBee gateway phone is not receiving pushes: heartbeat **104 minutes stale**,
`battery_optimization_exempt: false`. That is the actual cause of the hours-long
OTP delays — TextBee accepted every send while the phone dozed. With the fix live,
users now get an instant, understandable 503 instead of a silent multi-hour wait.

**Owner action to restore delivery:** charge/unlock the gateway phone, open the
TextBee app, and exempt it from battery optimization (Android Settings → Apps →
TextBee → Battery → Unrestricted). Confirm `gateway_reachable: true` on
`GET /api/auth/phone/status` before announcing availability.

## Tests (exit statuses, real runs)

| Suite | Result | Exit |
| --- | --- | --- |
| `experiments/client_model_audit/test_phone_otp_isolated.py` | 28/28 | 0 |
| `experiments/client_model_audit/test_textbee_response_handling.py` | 11/11 | 0 |
| `experiments/client_model_audit/test_textbee_gateway_guard.py` | 23/23 | 0 |
| `experiments/client_model_audit/test_textbee_retry_policy.py` | 32/32 | 0 |

All four ran against the exact deployed `phone_auth.py` hash; aggregate exit 0.
The suites pin the safety properties: retries reuse an identical payload (a retry can
never deliver a second code), 400/401 are never retried, ambiguous transport errors
consult TextBee's message history instead of resending blind, and a refused request
does not burn the cooldown.

## Android release

No rebuild required and none was made: nothing under `seediq-mobile/app` or
`seediq-mobile/src` is newer than the delivered APK, and the client already renders
this error immediately in all three languages ("SMS service is unavailable…" /
Hindi / Kannada) via its existing 503 provider-error path.

- [deliverables/SeedIQ-Android-v1.2.3-release.apk](deliverables/SeedIQ-Android-v1.2.3-release.apk)
  — 95,224,045 B, `ai.seediq.mobile` 1.2.3 (versionCode 7)
- SHA-256 `b13590ce11ee6e8f2b3da87381a0b30ea37f2b59a791bf07abb1449da0fa8649`
  (matches [the .sha256 file](deliverables/SeedIQ-Android-v1.2.3-release.apk.sha256))

## Still unverified / limitations

- **Real SMS receipt and code verification end-to-end**: blocked by the gateway phone
  being offline to TextBee. Once the owner wakes the phone, one OTP should be sent to
  the admin handset and the received code verified (4 digits, 300 s TTL).
- APK install/launch was verified on an x86_64 emulator; the client's ARM64 physical
  handset has not been exercised.
- The working tree still holds the uncommitted OTP fix (`SeedIQ/phone_auth.py` etc.);
  it was not committed or pushed.

## Rollback

```sh
cp /Users/apple/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-predeploy \
   /Users/apple/seediq-prod-deploy/SeedIQ-runtime.tar.xz
cd /Users/apple/seediq-prod-deploy && railway up --ci -y \
  -s 3bb53fa2-9171-4b97-bab2-c2cc6b508902 -e 74170432-2f3a-44b2-862c-03726e67fb65
```
