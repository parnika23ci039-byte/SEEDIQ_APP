# SeedIQ Android APK — delivery + verification (2026-10-15)

## 1. The file to hand over

| | |
|---|---|
| **APK** | `deliverables/SeedIQ-Android-v1.2.3-release.apk` |
| **Size** | 95,224,045 bytes (90.8 MiB) |
| **SHA-256** | `b13590ce11ee6e8f2b3da87381a0b30ea37f2b59a791bf07abb1449da0fa8649` |
| **Checksum file** | `deliverables/SeedIQ-Android-v1.2.3-release.apk.sha256` |
| **Package** | `ai.seediq.mobile` |
| **versionName / versionCode** | `1.2.3` / `7` |
| **minSdk / targetSdk / compileSdk** | 24 / 34 / 35 |
| **Signed with** | CN=SeedIQ, OU=Mobile, O=SeedIQ, L=Hyderabad, ST=Telangana, C=IN |
| **Signer cert SHA-256** | `84a121a7c13d8b580a2f6b1c5773c964ef3c500092e53b9d64dfcb4894f41403` |

Built from the current `seediq-mobile` sources with `:app:assembleRelease`
(`BUILD SUCCESSFUL in 1m 12s`, 527 tasks).

## 2. What was actually verified (not assumed)

| Check | How | Result |
|---|---|---|
| Signature schemes | `apksigner verify --verbose --min-sdk-version 23` | **v1 (JAR) ✓, v2 ✓, v3 ✓** — verifies |
| v1 really present on disk | `META-INF/CERT.SF`, `META-INF/CERT.RSA`, `META-INF/MANIFEST.MF` inside the zip | present (OEM installers that parse with `JarInputStream` will accept it) |
| Version identity | `aapt2 dump badging` | `ai.seediq.mobile` 1.2.3 (7), min 24 / target 34 |
| Embedded JS is current | SHA-256 of `assets/index.android.bundle` vs the freshly generated bundle | **identical** — `b7ebf3db781dc96cfc24c378ffcd94e9e4101f833860dc878a4dd7a9cd26bc65` |
| Newest app source vs bundle time | newest `app/`+`src/` file 2026-10-14 22:17:13, bundle 2026-10-15 00:28:52 | bundle is **newer than every source file** — nothing stale |
| Phone-auth client code inside the bundle | `strings` on the bundle | `api/auth/phone/request-otp`, `…/verify-otp`, `…/status`, `warmUpBackendWithin`, `AUTH_TIMEOUT_MS`, `sms_provider_not_configured` |
| Install on a device | `adb install -r` of **this exact deliverable file** | `Success`; `versionCode=7 versionName=1.2.3` |
| Launch | `adb shell monkey … LAUNCHER`, 18 s wait | process alive, `topResumedActivity=ai.seediq.mobile/.MainActivity`, `ReactNativeJS: Running "main"`, **no FATAL EXCEPTION / no RN error** |
| Renders the real UI | `uiautomator dump` | login screen with `Mobile number`, `+91`, `Send verification code`, "We'll send a 4-digit verification code", `Explore as guest (5 min)` |

Screenshot of the launched release build: `experiments/client_model_audit/apk_launch_2026-10-15.png`

Note on `apksigner`: with the APK's own `minSdkVersion=24` it reports
"v1 scheme: false" purely because v1 is *not required* at that minSdk and the
check is skipped. Forcing `--min-sdk-version 23` shows **v1 = true**, and the JAR
signature files are physically inside the APK, which is what matters for
sideloading via a file manager.

## 3. Install instructions for the client

1. Copy `SeedIQ-Android-v1.2.3-release.apk` to the phone (USB, Drive, email, or `adb install`).
2. On the phone: **Settings → Apps → Special access → Install unknown apps** → allow the app you are installing *from* (Files / Chrome / Drive).
3. Tap the APK → **Install** → open **SeedIQ**.
4. On Android 14: if the system shows *"App not installed"* with no reason, the APK was re-downloaded and corrupted — compare the SHA-256 above, or copy it again over USB.
5. Sign-in: enter the 10-digit number → **Send verification code** → enter the 4-digit code. `+91` is the default country code.

Requires Android 7.0 (API 24) or newer. No Play Store account needed.

## 4. IMPORTANT 
The codes are generated and sent by the **backend**, not by the app. Every OTP
change lives in `SeedIQ/phone_auth.py`, and that file is **not deployed**:

```
$ curl -s https://sublime-ambition-production-488f.up.railway.app/api/auth/phone/status
{"admin_phone_configured":true,"cooldown_seconds":20,"default_country_code":"91",
 "otp_length":4,"otp_ttl_seconds":300,"phone_auth":true,
 "sms_configured_providers":["textbee"],"sms_provider":"textbee","sms_ready":true,
 "status":"success"}                      <-- no "gateway_reachable" / "gateway" keys
```

The `gateway_reachable` / `gateway` diagnostics only exist in the local
(uncommitted) `phone_auth.py`, so the live server is still running the **old,
unguarded send path** — the one that accepts a code even when the TextBee
gateway phone is asleep, which is what produced the multi-hour delays.

**So: the APK alone does not fix the delay. The backend must be deployed too.**
Order does not matter for correctness; both are needed before a live retest.

## 5. Test evidence for the backend fix (offline, no SMS sent)

All four suites were run with `.freebuff/venv/bin/python`; exit status is the
source of truth:

| Suite | Result | Exit |
|---|---|---|
| `experiments/client_model_audit/test_phone_otp_isolated.py` | 28/28 passed | 0 |
| `experiments/client_model_audit/test_textbee_gateway_guard.py` | 23/23 passed | 0 |
| `experiments/client_model_audit/test_textbee_response_handling.py` | 11/11 passed | 0 |
| `experiments/client_model_audit/test_textbee_retry_policy.py` *(new)* | 32/32 passed | 0 |
| `python -m py_compile SeedIQ/phone_auth.py` | OK | 0 |

The new suite pins the retry/dedupe policy: retryable statuses
(408/425/429/5xx) are retried with an **identical payload** (so a retry can
never deliver a second, different code), bounded by `SEEDIQ_SMS_MAX_RETRIES`
(clamped to 4 extra attempts), honouring `Retry-After` up to a hard cap; 400/401
are **never** retried; a transport error or an unreadable body never triggers a
blind resend — TextBee's own message history decides, and an unreadable history
becomes `UNKNOWN` rather than a fake failure; and no response that says
"accepted" ever claims the SMS was delivered.

## 6. Controlled live retest (after deploying the backend)

1. Deploy `SeedIQ/phone_auth.py`; then `curl /api/auth/phone/status` must show
   `gateway_reachable` and a `gateway` object.
2. Install this APK on the target handset.
3. With the gateway phone healthy: request a code and time it end-to-end
   (`request-otp` response → SMS arrival). Baseline measured earlier: 0-30 s.
4. Put the gateway phone into Doze (screen off, unplugged, battery saver on) for
   >90 s, then request a code: the server must **refuse** with a clear reason
   instead of queueing a code that arrives hours later and expired.
5. Confirm no duplicate SMS when the provider returns 5xx mid-send, and that a
   `UNKNOWN` outcome is surfaced as "could not confirm", never as "sent".
