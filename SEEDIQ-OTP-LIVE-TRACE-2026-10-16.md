# SeedIQ OTP — live trace, corrected error reporting, and verification (2026-10-16)

Scope respected: only phone-OTP files changed — `SeedIQ/phone_auth.py`,
`seediq-mobile/src/lib/otp-errors.ts` (new), `seediq-mobile/src/lib/auth-context.tsx`,
the OTP strings in `src/i18n/{en,hi,kn}.ts`, and OTP tests. No AI/crop features,
navigation, language settings, unrelated login methods or other screens were touched.
No production secret or environment variable was read, printed or changed.

## 1. Exact root cause of the current error

**The message did not come from the backend's configuration state — it came from the
app's error mapping.** Two defects, both now fixed:

**Defect A (the client's message).** `seediq-mobile/src/lib/auth-context.tsx` treated
*any* HTTP 503 from `/api/auth/phone/request-otp` as a configuration problem:

```ts
const isProvider = e.code === "sms_provider_not_configured"
  || e.code === "sms_delivery_failed" || e.status === 503;   // <-- any 503
error: isProvider ? translate("phoneAuth.smsProviderError") : ...
// "SMS service is unavailable or not configured on the server. Please retry…"
```

So when the backend correctly answered `503 sms_gateway_unavailable` ("the gateway
phone is not receiving"), the app threw that reason away and told the user the service
was **unconfigured**. That is exactly the string the client reported.

**Defect B (backend wording/code reuse).** One code (`sms_gateway_unavailable`) and one
message ("the gateway phone is not reachable") were used for all three block reasons,
including `no_enabled_device` and `device_disabled`, which are device-state problems,
not reachability.

**Ruled out with evidence (checked against code and live logs, not assumed):**

| Possibility | Verdict |
| --- | --- |
| APK points at an old/wrong backend | No — `src/lib/config.ts` defaults to the Railway URL and the shipped bundle contains `https://sublime-ambition-production-488f.up.railway.app` (1 hit, no stale Vercel/ngrok/local URLs) |
| Wrong endpoint or request body | No — app POSTs `/api/auth/phone/request-otp` with `{phone, purpose}`, matching the Flask route |
| Missing/misparsed TextBee config | No — live `/status` reports `sms_provider: textbee`, `sms_ready: true`, `sms_configured_providers: ["textbee"]`, and the preflight returns real device data (`device_id`, heartbeat, power info) |
| Health logic reports SMS as unconfigured | No — it reported `gateway_not_receiving`, never a configuration error |
| Frontend maps 503 to "not configured" | **Yes — this was the defect** |
| Deployed code differs from tested code | No — deployed `phone_auth.py` hash equals the tested file |
| Exception / CORS / connectivity | No — the app's own calls succeed (`GET /api/health 200`, `GET /api/me 200`) and it parsed the 503 JSON body |

## 2. Files changed and why

| File | Why |
| --- | --- |
| `SeedIQ/phone_auth.py` | `_TEXTBEE_BLOCK_RESPONSES` maps each block reason to its own code + message: `sms_no_device`, `sms_device_disabled`, `sms_gateway_unavailable` (the refusal branch now uses it) |
| `seediq-mobile/src/lib/otp-errors.ts` (new) | Pure, dependency-free mapping: code → localized key, plus server-message fallback for unknown codes; `isOtpProviderFailure()` classification |
| `seediq-mobile/src/lib/auth-context.tsx` | Uses that mapping instead of the blanket 503 → "not configured" branch |
| `seediq-mobile/src/i18n/{en,hi,kn}.ts` | One accurate string per reason in all three shipped locales; the generic string no longer claims "not configured" |
| `experiments/client_model_audit/test_textbee_gateway_guard.py` | Pins the distinct codes/messages per reason |
| `seediq-mobile/tests/otp-errors.test.mjs` (new) | Regression test for the mapping + translation coverage |

## 3. Before and after

**Before** (client-visible, live, 01:34–01:44 UTC) — status 503, sanitized body:

```json
{"status":"error","code":"sms_gateway_unavailable",
 "message":"The SMS gateway phone is not reachable right now, so no code was sent and nothing was queued. Please try again in a few minutes.",
 "gateway":{"reason":"gateway_not_receiving","unacknowledged_age_seconds":184.3,"unacknowledged_to":"+91*****2930"}}
```
…but the app rendered: *"SMS service is unavailable or not configured on the server.
Please retry or contact support."*

**After** — same request, same 503, app on the emulator now renders (screenshot:
[otp_error_on_device_2026-10-16.png](experiments/client_model_audit/otp_error_on_device_2026-10-16.png)):

> **"The SMS gateway phone is not reachable right now, so no code was sent. Please try
> again in a few minutes."** — with a **Retry** button

Server-side record of that exact app request:

```
2026-10-15T20:46:33Z  POST /api/auth/phone/request-otp  503  1569ms
```

The new backend codes, exercised in tests and returned per reason:
`sms_provider_not_configured` (no provider) · `sms_no_device` · `sms_device_disabled` ·
`sms_gateway_unavailable` (phone not receiving) · `sms_delivery_failed` (provider
rejected) · success = `{"status":"success","delivery":"accepted"}` (acceptance only —
never a delivery claim).

## 4. Tests — exact counts and exit statuses

| Check | Result | Exit |
| --- | --- | --- |
| `test_phone_otp_isolated.py` | 28/28 | 0 |
| `test_textbee_response_handling.py` | 11/11 | 0 |
| `test_textbee_gateway_guard.py` | 29/29 (was 26) | 0 |
| `test_textbee_retry_policy.py` | 32/32 | 0 |
| `seediq-mobile/tests/otp-errors.test.mjs` | 10/10 checks | 0 |
| `npm run typecheck` (`tsc --noEmit`) | clean | 0 |
| `./gradlew assembleRelease` | BUILD SUCCESSFUL (1m51s) | 0 |

The mobile test asserts, among others: gateway-unavailable maps to its **own** message
(not "not configured"); no-device and disabled-device differ; unknown codes fall back to
the server's message; provider failures are classified while 400/429 are not; every
emitted key exists in en, hi and kn; and **no locale still describes a gateway problem
as a configuration problem**. Assertions were added/corrected, never weakened.

## 5. Deployment and live verification

- Backend deployment `9b4d90e8-fb37-4f0b-8fe0-3b958a748cb8` → **SUCCESS**
  (`SeedIQ Backend` / `production` / `sublime-ambition`); previous `ff82fdf8` REMOVED.
  Archive SHA-256 `1dd855393944a87a7b5ceb5b848a2ff27fdd6097da22664ef9f3431e44b084f9`;
  only `phone_auth.py` changed (identical 203-entry list); archived hash
  `1b1bbdc5…` equals the tested repo file. Rollback:
  `~/seediq-prod-deploy-backups/SeedIQ-runtime.tar.xz.bak-2026-10-16-v3-predeploy`.
- APK rebuilt and replaced:
  [deliverables/SeedIQ-Android-v1.2.3-release.apk](deliverables/SeedIQ-Android-v1.2.3-release.apk)
  — 95,227,044 B, `ai.seediq.mobile` 1.2.3 (versionCode 7), SHA-256
  `ecc2bbd0e6230ad606712d3946394a4d7a55845df012fb276b973c3909d16edf` (also in the
  `.sha256` file), v1+v2+v3 signatures verified. The embedded bundle contains all four
  new messages and **zero** occurrences of the old "unavailable or not configured"
  string.
- On-device verification: installed this exact file (`adb install -r` → `Success`),
  launched, drove the real login screen, requested a code, and read the rendered
  message (above). No crash and no JS errors in logcat.

## 6. Did the SMS reach the handset?

**No.** The current request was refused *before* any send (nothing queued, no cooldown
burned), and the earlier accepted message was never acknowledged by the gateway phone —
the provider's own record shows it unacknowledged (`+91*****2930`). This is the
documented TextBee behaviour for a phone whose app is paused; the message waits until
the phone returns, by which time a 300 s code is expired.

## 7. Remaining client-side/external dependency

The TextBee Android gateway phone must be awake and receiving. Software cannot bridge
it: TextBee has no cloud relay, and no alternative provider is configured
(`sms_configured_providers: ["textbee"]` — MSG91/Twilio/Fast2SMS/webhook adapters exist
in code but have no credentials, and none were invented).

Owner action (≈2 minutes, no deploy): charge/unlock the phone, open the TextBee app and
set Android → Apps → TextBee → Battery → **Unrestricted**. Then
`GET /api/auth/phone/status` flips to `gateway_reachable: true`, `send_blocked: false`
automatically and phone login works. Optional longer-term: register a second Android
phone in TextBee as the default device, or configure one existing adapter.
