// OTP provider-failure mapping — the single place that decides what the user is
// told when the backend refuses to send a verification code.
//
// The backend answers with an accurate, machine-readable reason:
//   sms_provider_not_configured -> the server really has no SMS provider
//   sms_no_device               -> no gateway device is enabled
//   sms_device_disabled         -> the gateway device is disabled
//   sms_gateway_unavailable     -> the gateway phone is not receiving right now
//   sms_delivery_failed         -> the provider rejected or failed the send
//
// Before 2026-10-16 every 503 was rendered with one blanket string ("SMS service
// is unavailable or not configured on the server"), so users were told the
// service was *unconfigured* while the server was actually reporting that the
// gateway phone was not receiving. Each code now maps to its own message, and an
// unknown provider failure falls back to the server's own `message` rather than
// inventing a configuration problem.
//
// This module is intentionally dependency-free (no React, no i18n import) so it
// can be unit-tested outside React Native — see tests/otp-errors.test.mjs.

export const OTP_PROVIDER_ERROR_KEYS = {
  notConfigured: "phoneAuth.smsNotConfigured",
  noDevice: "phoneAuth.smsNoDevice",
  deviceDisabled: "phoneAuth.smsDeviceDisabled",
  gatewayUnavailable: "phoneAuth.smsGatewayUnavailable",
  deliveryFailed: "phoneAuth.smsDeliveryFailed",
} as const;

export type OtpProviderErrorKey =
  (typeof OTP_PROVIDER_ERROR_KEYS)[keyof typeof OTP_PROVIDER_ERROR_KEYS];

const CODE_TO_KEY: Record<string, OtpProviderErrorKey> = {
  sms_provider_not_configured: OTP_PROVIDER_ERROR_KEYS.notConfigured,
  sms_no_device: OTP_PROVIDER_ERROR_KEYS.noDevice,
  sms_device_disabled: OTP_PROVIDER_ERROR_KEYS.deviceDisabled,
  sms_gateway_unavailable: OTP_PROVIDER_ERROR_KEYS.gatewayUnavailable,
  sms_delivery_failed: OTP_PROVIDER_ERROR_KEYS.deliveryFailed,
};

/** i18n key for a backend OTP failure code, or null when the code is unknown. */
export function otpProviderErrorKey(code?: string | null): OtpProviderErrorKey | null {
  if (!code) return null;
  return CODE_TO_KEY[code] ?? null;
}

/**
 * True for failures raised by the SMS layer (so the caller can mark the error as
 * a provider error rather than a user mistake). Unknown 502/503 responses still
 * count, but their text must come from the server, never from a local guess.
 */
export function isOtpProviderFailure(
  status?: number | null,
  code?: string | null,
): boolean {
  if (code && code in CODE_TO_KEY) return true;
  return status === 502 || status === 503;
}

/**
 * The exact text to show for a provider failure.
 *
 * Prefers the localized message for a known code, then the server's own
 * `message`, and only as a last resort the generic provider string.
 */
/** Keys this module can ask the app's i18n layer to render. */
export type OtpProviderMessageKey = OtpProviderErrorKey | "phoneAuth.smsProviderError";

export function otpProviderErrorMessage(
  translate: (key: OtpProviderMessageKey) => string,
  status?: number | null,
  code?: string | null,
  serverMessage?: string | null,
): string {
  const key = otpProviderErrorKey(code);
  if (key) return translate(key);
  const server = (serverMessage || "").trim();
  if (server) return server;
  return translate("phoneAuth.smsProviderError");
}
