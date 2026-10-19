// Regression test for the OTP provider-error mapping (2026-10-16).
//
// Defect it pins: every 503 from /api/auth/phone/request-otp used to be rendered
// with one blanket string claiming the service was "not configured", so the app
// showed "SMS service is unavailable or not configured on the server" while the
// backend was actually reporting that the TextBee gateway phone was not
// receiving. The mapping must now surface the real reason.
//
// No test framework is added: the pure module is compiled with the project's own
// TypeScript and executed under Node. Exit status is the source of truth.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
let failures = 0;

function check(name, fn) {
  try {
    fn();
    console.log(`  [PASS] ${name}`);
  } catch (e) {
    failures += 1;
    console.log(`  [FAIL] ${name} — ${e.message}`);
  }
}

// 1. Compile the real module (no tsconfig project, single file, ESM output).
const outDir = mkdtempSync(path.join(tmpdir(), "otp-errors-"));
execFileSync(
  path.join(root, "node_modules", ".bin", "tsc"),
  [
    path.join("src", "lib", "otp-errors.ts"),
    "--outDir",
    outDir,
    "--module",
    "esnext",
    "--target",
    "es2020",
    "--moduleResolution",
    "bundler",
    "--skipLibCheck",
  ],
  { cwd: root, stdio: "pipe" },
);

const compiled = readdirSync(outDir).find((f) => f.endsWith(".js"));
assert.ok(compiled, "tsc produced no output for src/lib/otp-errors.ts");
renameSync(path.join(outDir, compiled), path.join(outDir, "mod.mjs"));
const mod = await import(pathToFileURL(path.join(outDir, "mod.mjs")).href);

const {
  OTP_PROVIDER_ERROR_KEYS: KEYS,
  otpProviderErrorKey,
  otpProviderErrorMessage,
  isOtpProviderFailure,
} = mod;

const translate = (key) => `t:${key}`;

console.log("=".repeat(78));
console.log("OTP provider-error mapping — mobile regression test");
console.log("=".repeat(78));

check("gateway-not-receiving maps to its OWN message, not 'not configured'", () => {
  assert.equal(otpProviderErrorKey("sms_gateway_unavailable"), KEYS.gatewayUnavailable);
  assert.notEqual(otpProviderErrorKey("sms_gateway_unavailable"), KEYS.notConfigured);
});

check("genuinely unconfigured service still maps to the configuration message", () => {
  assert.equal(otpProviderErrorKey("sms_provider_not_configured"), KEYS.notConfigured);
});

check("no-device and disabled-device are distinguished from each other", () => {
  assert.equal(otpProviderErrorKey("sms_no_device"), KEYS.noDevice);
  assert.equal(otpProviderErrorKey("sms_device_disabled"), KEYS.deviceDisabled);
  assert.notEqual(otpProviderErrorKey("sms_no_device"), otpProviderErrorKey("sms_device_disabled"));
});

check("provider send failure has its own message", () => {
  assert.equal(otpProviderErrorKey("sms_delivery_failed"), KEYS.deliveryFailed);
});

check("unknown failure code falls back to the server's own message", () => {
  assert.equal(otpProviderErrorKey("sms_something_new"), null);
  assert.equal(
    otpProviderErrorMessage(translate, 503, "sms_something_new", "Server says exactly this."),
    "Server says exactly this.",
  );
});

check("unknown 503 without a server message keeps the generic provider text", () => {
  assert.equal(otpProviderErrorMessage(translate, 503, undefined, ""), "t:phoneAuth.smsProviderError");
});

check("known codes win over a server message (localized UI text)", () => {
  assert.equal(
    otpProviderErrorMessage(translate, 503, "sms_gateway_unavailable", "raw server text"),
    "t:phoneAuth.smsGatewayUnavailable",
  );
});

check("provider failures are classified, user mistakes are not", () => {
  assert.equal(isOtpProviderFailure(503, "sms_gateway_unavailable"), true);
  assert.equal(isOtpProviderFailure(502, "sms_delivery_failed"), true);
  assert.equal(isOtpProviderFailure(503, undefined), true);
  assert.equal(isOtpProviderFailure(400, "invalid_phone"), false);
  assert.equal(isOtpProviderFailure(429, "cooldown"), false);
  assert.equal(isOtpProviderFailure(200, undefined), false);
});

// Every key the mapping can emit must exist in all three shipped locales.
const locales = ["en", "hi", "kn"];
const sources = Object.fromEntries(
  locales.map((l) => [l, readFileSync(path.join(root, "src", "i18n", `${l}.ts`), "utf8")]),
);
const emittedKeys = Object.values(KEYS);

check("every emitted key exists in en, hi and kn", () => {
  for (const [locale, source] of Object.entries(sources)) {
    for (const key of emittedKeys) {
      const name = key.split(".").pop();
      assert.ok(
        new RegExp(`\\b${name}\\s*:`).test(source),
        `${locale}.ts is missing ${name}`,
      );
    }
  }
});

check("no locale still calls a gateway problem a configuration problem", () => {
  // The blanket string that caused the misreport must no longer claim
  // "not configured" in any language.
  for (const [locale, source] of Object.entries(sources)) {
    const match = source.match(/smsProviderError:\s*\n?\s*"([^"]+)"/);
    assert.ok(match, `${locale}.ts has no smsProviderError string`);
    const text = match[1];
    assert.ok(
      !/not configured|कॉन्फ़िगर|ಕಾನ್ಫಿಗರ್/.test(text),
      `${locale}.ts still reports a configuration problem: ${text}`,
    );
  }
});

console.log("=".repeat(78));
if (failures) {
  console.log(`OTP ERROR MAPPING: ${failures} check(s) FAILED`);
  process.exit(1);
}
console.log("OTP ERROR MAPPING: all checks passed");
