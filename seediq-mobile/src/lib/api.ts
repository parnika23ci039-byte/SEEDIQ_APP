import { API_BASE_URL } from "./config";
import { translate } from "../i18n";

/**
 * Centralized API client for the SeedIQ Flask backend.
 *
 * The backend authenticates via signed session cookies (Flask session) with
 * `CORS(app, supports_credentials=True)`, so every request must send
 * credentials. Mobile devices also expose a working `fetch` with credentials.
 *
 * TIMEOUTS: the deployed backend runs on Render, which parks idle containers
 * and then takes tens of seconds to answer the first request ("cold start").
 * A short timeout therefore produced false "Network error" / "Request timed
 * out" failures on login and registration. Reads use a moderate timeout;
 * authentication uses a long one and may retry once.
 */

/** Reads (dashboard, weather, AI modules) — warm backend answers in ~2s. */
export const DEFAULT_TIMEOUT_MS = 30000;
/** Login, OTP, password reset — must survive a Render cold start. */
export const AUTH_TIMEOUT_MS = 60000;

export class ApiError extends Error {
  status: number;
  /** Machine-readable reason from the backend (`data.code`), when supplied. */
  code?: string;
  /** Seconds the caller should wait before retrying (rate limits). */
  retryAfter?: number;
  constructor(message: string, status: number, code?: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

export class NetworkError extends Error {
  constructor(message = translate("errors.network")) {
    super(message);
    this.name = "NetworkError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
  /** Extra attempts after a network-level/timeout failure (default 0). */
  retries?: number;
}

// ---------------------------------------------------------------------------
// Backend warm-up — wakes a parked Render container before we need it.
// ---------------------------------------------------------------------------

let warmUpPromise: Promise<boolean> | null = null;

/**
 * Fire-and-forget ping of `/api/health`. Safe to call repeatedly: concurrent
 * callers share one request. Never throws.
 */
export function warmUpBackend(): Promise<boolean> {
  if (warmUpPromise) return warmUpPromise;

  warmUpPromise = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 75000);
    try {
      const res = await fetch(`${API_BASE_URL}/api/health`, {
        method: "GET",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      clearTimeout(timer);
      // Allow a later warm-up (e.g. after a long background pause).
      setTimeout(() => {
        warmUpPromise = null;
      }, 120000);
    }
  })();

  return warmUpPromise;
}

/** Warm the backend but never make the UI wait longer than `maxWaitMs`. */
export async function warmUpBackendWithin(maxWaitMs: number): Promise<void> {
  await Promise.race([
    warmUpBackend(),
    new Promise<void>((resolve) => setTimeout(resolve, maxWaitMs)),
  ]);
}

// ---------------------------------------------------------------------------
// Request
// ---------------------------------------------------------------------------

export async function api<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    formData,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    retries = 0,
  } = options;

  let lastNetworkError: NetworkError | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res: Response;
    try {
      res = await fetch(`${API_BASE_URL}${path}`, {
        method,
        credentials: "include",
        signal: controller.signal,
        headers: formData
          ? undefined // let RN set multipart boundary
          : {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
        body: formData ? formData : body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e: any) {
      clearTimeout(timer);
      const aborted = e?.name === "AbortError" || e?.name === "TimeoutError";
      lastNetworkError = new NetworkError(
        aborted ? translate("errors.timeout") : translate("errors.network"),
      );
      if (attempt < retries) {
        // A timed-out first attempt usually means the container just woke up.
        await warmUpBackendWithin(8000);
        continue;
      }
      throw lastNetworkError;
    }
    clearTimeout(timer);

    const isJson = (res.headers.get("content-type") || "").includes("application/json");
    const data = isJson ? await res.json().catch(() => null) : null;

    if (!res.ok) {
      const message =
        (data && (data.message || data.error || (typeof data === "string" ? data : null))) ||
        resTextFallback(res.status);
      throw new ApiError(
        String(message),
        res.status,
        data && typeof data === "object" ? data.code : undefined,
        data && typeof data === "object" ? data.retry_after : undefined,
      );
    }

    if (data && typeof data === "object" && data.status === "error") {
      throw new ApiError(String(data.message || translate("errors.requestFailed")), res.status);
    }

    return data as T;
  }

  // Unreachable — the loop either returns or throws.
  throw lastNetworkError ?? new NetworkError();
}

function resTextFallback(status: number): string {
  if (status === 401) return translate("errors.unauthorized");
  if (status === 403) return translate("errors.forbidden");
  if (status === 404) return translate("errors.notFound");
  if (status >= 500) return translate("errors.serverError");
  return translate("errors.httpFailed", { status });
}
