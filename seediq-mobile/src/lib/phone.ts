/**
 * Phone-number helpers for the phone-first sign-in flow.
 *
 * The UI collects a national number plus a country dial code; the backend
 * receives E.164. Validation mirrors the server (`phone_auth.normalize_phone`)
 * so a typo is caught before an SMS is ever billed.
 */

export interface DialCode {
  /** ISO 3166-1 alpha-2, used only for the label. */
  iso: string;
  dial: string;
  country: string;
}

/**
 * India first (the client's market); a short list so the picker stays usable.
 * The implementation is country-code agnostic — the backend normalises any
 * E.164 number — so extending this list is all a new market needs.
 */
export const DIAL_CODES: DialCode[] = [
  { iso: "IN", dial: "+91", country: "India" },
  { iso: "US", dial: "+1", country: "United States" },
  { iso: "GB", dial: "+44", country: "United Kingdom" },
  { iso: "AE", dial: "+971", country: "United Arab Emirates" },
  { iso: "SG", dial: "+65", country: "Singapore" },
  { iso: "AU", dial: "+61", country: "Australia" },
];

export const DEFAULT_DIAL_CODE = "+91";

/** Digit groups that should not be offered in the picker (reserved/testing). */
const MAX_NATIONAL_DIGITS = 14;

/** Strip everything that is not a digit. */
export function digitsOnly(value: string): string {
  return (value ?? "").replace(/\D/g, "");
}

/**
 * Drop a leading national trunk `0` ("091102 52930" -> "9110252930") the same
 * way the backend does, so what the user sees and what is sent agree.
 */
export function normalizeNational(value: string): string {
  const digits = digitsOnly(value);
  if (digits.length === 11 && digits.startsWith("0")) return digits.slice(1);
  return digits;
}

export interface PhoneValidation {
  valid: boolean;
  /** E.164 without a leading '+', ready for the backend. */
  e164: string | null;
  /** Key of the error message to show, or null when valid. */
  errorKey: "phoneAuth.errRequired" | "phoneAuth.errInvalid" | null;
}

export function validatePhone(national: string, dial: string = DEFAULT_DIAL_CODE): PhoneValidation {
  const digits = normalizeNational(national);
  if (!digits) return { valid: false, e164: null, errorKey: "phoneAuth.errRequired" };

  const country = digitsOnly(dial) || "91";
  let full = digits;
  if (digits.length === 10) full = country + digits;
  else if (digits.startsWith(country) && digits.length > country.length + 6) full = digits;

  if (full.length < 8 || full.length > MAX_NATIONAL_DIGITS + country.length) {
    return { valid: false, e164: null, errorKey: "phoneAuth.errInvalid" };
  }
  // India: mobile numbers start 6-9 and are exactly 10 digits.
  if (country === "91") {
    const national10 = digits.length === 10 ? digits : full.slice(2);
    if (!/^[6-9]\d{9}$/.test(national10)) {
      return { valid: false, e164: null, errorKey: "phoneAuth.errInvalid" };
    }
    return { valid: true, e164: "91" + national10, errorKey: null };
  }
  return { valid: true, e164: full, errorKey: null };
}

/** "9110252930" -> "91102 52930" (Indian 5+5 grouping, as printed on SIM cards). */
export function formatNational(national: string, dial: string = DEFAULT_DIAL_CODE): string {
  const digits = normalizeNational(national);
  if (digitsOnly(dial) === "91" && digits.length === 10) {
    return `${digits.slice(0, 5)} ${digits.slice(5)}`;
  }
  return digits.replace(/(\d{3})(?=\d)/g, "$1 ");
}

/** "+91 91102 52930" — the form the backend echoes back. */
export function prettyPhone(e164: string | null | undefined, dial: string = DEFAULT_DIAL_CODE): string {
  if (!e164) return "";
  const country = digitsOnly(dial) || "91";
  if (e164.startsWith(country)) {
    const national = e164.slice(country.length);
    return `${dial} ${formatNational(national, dial)}`;
  }
  return `+${e164}`;
}

/** Log/UI-safe reference: "+91*****2930". */
export function maskPhone(e164: string | null | undefined): string {
  if (!e164 || e164.length <= 6) return "+*****";
  return `+${e164.slice(0, 2)}*****${e164.slice(-4)}`;
}
