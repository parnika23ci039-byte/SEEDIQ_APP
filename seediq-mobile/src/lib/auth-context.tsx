import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  api,
  ApiError,
  NetworkError,
  AUTH_TIMEOUT_MS,
  warmUpBackend,
  warmUpBackendWithin,
} from "./api";
import { supabaseAuth } from "./supabase";
import { GUEST_DURATION_SECONDS, STORAGE_KEYS } from "./config";
import { isOtpProviderFailure, otpProviderErrorMessage } from "./otp-errors";
import { translate } from "../i18n";
import type { User, UserRole } from "./types";

export type { User, UserRole };

interface AuthResult {
  success: boolean;
  user?: User;
  error?: string;
}

interface MessageResult {
  success: boolean;
  message?: string;
  error?: string;
}

/**
 * Result of asking the backend to send a 4-digit code.
 *
 * `blocked` is true when the request failed because the deployment cannot
 * deliver SMS (endpoint missing, or no provider configured). The UI shows the
 * precise reason instead of a generic failure, and never pretends a code was
 * sent.
 */
interface PhoneOtpResult extends MessageResult {
  blocked?: boolean;
  retryAfter?: number;
  otpLength?: number;
  phone?: string;
  requestId?: string;
  isProviderError?: boolean;
}

/** Capability probe for `GET /api/auth/phone/status`. */
export interface PhoneAuthStatus {
  available: boolean;
  smsReady: boolean;
  otpLength: number;
  provider: string | null;
  /** Why it is unavailable: missing endpoint, disabled, or unreachable. */
  reason?: "missing" | "error" | "offline";
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  /** True once the stored session has been restored (or cleared) on startup. */
  sessionRestored: boolean;
  guestTimeRemaining: number | null;
  formatGuestTime: (seconds: number | null) => string;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  requestPhoneOtp: (
    phone: string,
    purpose?: "login" | "register",
    name?: string,
  ) => Promise<PhoneOtpResult>;
  verifyPhoneOtp: (phone: string, code: string, name?: string, requestId?: string) => Promise<AuthResult>;
  phoneAuthStatus: PhoneAuthStatus | null;
  refreshPhoneAuthStatus: () => Promise<PhoneAuthStatus>;
  requestRegistrationOtp: (name: string, email: string, password: string) => Promise<MessageResult>;
  verifyRegistrationOtp: (email: string, otp: string) => Promise<AuthResult>;
  requestPasswordResetOtp: (email: string) => Promise<MessageResult>;
  verifyPasswordResetOtp: (email: string, otp: string) => Promise<MessageResult>;
  resetPassword: (email: string, otp: string, newPassword: string) => Promise<MessageResult>;
  loginAsGuest: () => Promise<AuthResult>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<boolean>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function resolveRole(
  email: string | undefined,
  username: string | undefined,
  fallback: UserRole | string | undefined,
): UserRole {
  const e = (email || "").toLowerCase();
  const u = (username || "").toLowerCase();
  if (e === "admin@seediq.ai" || u === "admin") return "Admin";
  if (e === "researcher@quantum.org" || u === "researcher") return "Researcher";
  const f = (fallback || "Farmer") as UserRole;
  return ["Admin", "Researcher", "Farmer", "Guest"].includes(f) ? f : "Farmer";
}

function toUser(raw: Record<string, any>, fallbackEmail?: string): User {
  const email = raw.email || fallbackEmail || "";
  const username = raw.username || email.split("@")[0] || "user";
  const role = resolveRole(email, username, raw.role);
  return {
    id: raw.id ?? 0,
    username,
    email,
    name: raw.display_name || raw.name || username,
    display_name: raw.display_name || username,
    role,
    isGuest: raw.isGuest ?? role === "Guest",
    provider: raw.provider || "local",
    phone: raw.phone ? String(raw.phone) : undefined,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionRestored, setSessionRestored] = useState(false);
  const [guestTimeRemaining, setGuestTimeRemaining] = useState<number | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const clearStorage = useCallback(async () => {
    await AsyncStorage.multiRemove([
      STORAGE_KEYS.user,
      STORAGE_KEYS.guestExpiry,
      STORAGE_KEYS.supabaseToken,
    ]).catch(() => {});
  }, []);

  const persist = useCallback(async (u: User) => {
    setUser(u);
    await AsyncStorage.setItem(STORAGE_KEYS.user, JSON.stringify(u));
  }, []);

  // Restore persisted session on app start, then validate against /api/me.
  useEffect(() => {
    // Wake the Render container immediately at app start so a parked backend
    // is ready (or nearly ready) by the time the user submits the login form.
    void warmUpBackend();

    (async () => {
      let restored: User | null = null;
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEYS.user);
        if (saved) restored = JSON.parse(saved);
      } catch {
        // ignore corrupt storage
      }

      if (restored?.isGuest) {
        const expiryStr = await AsyncStorage.getItem(STORAGE_KEYS.guestExpiry).catch(() => null);
        const expiresAt = expiryStr ? parseInt(expiryStr, 10) : 0;
        if (!expiresAt || expiresAt <= Date.now()) {
          await clearStorage();
          setIsLoading(false);
          setSessionRestored(true);
          return;
        }
      }

      setUser(restored);
      setIsLoading(false);
      setSessionRestored(true);

      // Validate the cookie session with the backend (non-blocking for UI).
      try {
        const me = await api<{ authenticated: boolean; user?: Record<string, any> }>("/api/me", {
          timeoutMs: 15000,
        });
        if (!mounted.current) return;
        if (me.authenticated && me.user && !restored?.isGuest) {
          const fresh = toUser(me.user);
          setUser(fresh);
          await AsyncStorage.setItem(STORAGE_KEYS.user, JSON.stringify(fresh));
        }
      } catch {
        // Backend unreachable — keep the locally-restored user (web app does the same).
      }

      // Fallback: Supabase cloud session if we hold a token and no local user.
      if (!restored) {
        const token = await AsyncStorage.getItem(STORAGE_KEYS.supabaseToken).catch(() => null);
        if (token) {
          const supaUser = await supabaseAuth.getUser(token);
          if (supaUser?.id && mounted.current) {
            const email = (supaUser.email || "").toLowerCase();
            const fresh = toUser({
              id: supaUser.id,
              username: supaUser.user_metadata?.username || email.split("@")[0],
              email: supaUser.email,
              display_name: supaUser.user_metadata?.display_name || supaUser.user_metadata?.name,
              role: supaUser.user_metadata?.role || "Farmer",
              provider: "supabase",
            });
            setUser(fresh);
            await AsyncStorage.setItem(STORAGE_KEYS.user, JSON.stringify(fresh));
          }
        }
      }
    })();
  }, [clearStorage]);

  // Guest countdown timer with auto-logout at zero (5-minute max, like the web app).
  useEffect(() => {
    if (!user || !(user.isGuest || user.role === "Guest")) {
      setGuestTimeRemaining(null);
      return;
    }

    let interval: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    (async () => {
      let expiresAt: number;
      const saved = await AsyncStorage.getItem(STORAGE_KEYS.guestExpiry).catch(() => null);
      if (saved) {
        expiresAt = parseInt(saved, 10);
      } else {
        expiresAt = Date.now() + GUEST_DURATION_SECONDS * 1000;
        await AsyncStorage.setItem(STORAGE_KEYS.guestExpiry, String(expiresAt));
      }
      if (cancelled) return;

      const tick = () => {
        const remaining = Math.max(0, Math.floor((expiresAt - Date.now()) / 1000));
        if (mounted.current) {
          setGuestTimeRemaining(remaining);
        }
        if (remaining <= 0) {
          if (interval) clearInterval(interval);
          if (mounted.current) {
            void doLogoutInternal();
          }
        }
      };
      tick();
      interval = setInterval(tick, 1000);
    })();

    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, user?.isGuest]);

  const formatGuestTime = useCallback((seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }, []);

  // 1. Sign in — Flask backend first (sets the session cookie), Supabase fallback.
  const signIn = useCallback(async (email: string, password: string): Promise<AuthResult> => {
    setIsLoading(true);
    try {
      const raw = email.trim().toLowerCase();
      const normalized =
        raw === "admin" ? "admin@seediq.ai" : raw === "researcher" ? "researcher@quantum.org" : raw;

      // Remember a transport-level failure so a second, unrelated failure from
      // the Supabase fallback cannot mask the real diagnosis.
      let backendNetworkError: NetworkError | null = null;

      try {
        const data = await api<{ status: string; user?: Record<string, any>; message?: string }>(
          "/api/login",
          // 60s + one retry: the first request may hit a parked container.
          { method: "POST", body: { email: normalized, password }, timeoutMs: AUTH_TIMEOUT_MS, retries: 1 },
        );
        if (data.status === "success" && data.user) {
          const u = toUser(data.user, normalized);
          await persist(u);
          return { success: true, user: u };
        }
        return { success: false, error: data.message || translate("errors.authInvalid") };
      } catch (e) {
        if (e instanceof ApiError) {
          return { success: false, error: e.message };
        }
        if (e instanceof NetworkError) backendNetworkError = e;
        // Network-level failure → fall through to Supabase direct auth.
      }

      const { data: supa, error: supaErr } = await supabaseAuth.signInWithPassword(normalized, password);
      if (supaErr || !supa) {
        if (backendNetworkError) return { success: false, error: backendNetworkError.message };
        return { success: false, error: supaErr?.message || translate("errors.authInvalid") };
      }
      if (supa.access_token) {
        await AsyncStorage.setItem(STORAGE_KEYS.supabaseToken, supa.access_token);
      }
      const u = toUser({
        id: supa.user?.id || `supa_${Date.now()}`,
        username: supa.user?.user_metadata?.username || normalized.split("@")[0],
        email: supa.user?.email || normalized,
        display_name:
          supa.user?.user_metadata?.display_name ||
          supa.user?.user_metadata?.name ||
          normalized.split("@")[0],
        role: supa.user?.user_metadata?.role || "Farmer",
        provider: "supabase",
      });
      await persist(u);
      return { success: true, user: u };
    } catch (e: any) {
      if (e instanceof NetworkError) return { success: false, error: e.message };
      return { success: false, error: e?.message || translate("errors.authUnreachable") };
    } finally {
      setIsLoading(false);
    }
  }, [persist]);

  // -------------------------------------------------------------------------
  // Phone-number authentication — the primary flow.
  //
  // The phone number is the account identifier and a 4-digit code is the only
  // credential. Codes are issued and verified by the backend; the app never
  // invents one. When the deployment cannot deliver SMS the caller is told
  // exactly that (`blocked: true`) rather than being shown a fake success.
  // -------------------------------------------------------------------------

  const [phoneAuthStatus, setPhoneAuthStatus] = useState<PhoneAuthStatus | null>(null);

  const refreshPhoneAuthStatus = useCallback(async (): Promise<PhoneAuthStatus> => {
    try {
      const data = await api<{
        phone_auth?: boolean;
        sms_ready?: boolean;
        otp_length?: number;
        sms_provider?: string | null;
      }>("/api/auth/phone/status", { timeoutMs: 20000 });
      const status: PhoneAuthStatus = {
        available: data.phone_auth !== false,
        smsReady: !!data.sms_ready,
        otpLength: data.otp_length || 4,
        provider: data.sms_provider ?? null,
      };
      if (mounted.current) setPhoneAuthStatus(status);
      return status;
    } catch (e) {
      const status: PhoneAuthStatus = {
        available: false,
        smsReady: false,
        otpLength: 4,
        provider: null,
        reason:
          e instanceof ApiError
            ? e.status === 404
              ? "missing"
              : "error"
            : "offline",
      };
      if (mounted.current) setPhoneAuthStatus(status);
      return status;
    }
  }, []);

  // Probe once the session restore settles; never blocks the first paint.
  useEffect(() => {
    if (!sessionRestored) return;
    void refreshPhoneAuthStatus();
  }, [sessionRestored, refreshPhoneAuthStatus]);

  const requestPhoneOtp = useCallback(
    async (phone: string, purpose: "login" | "register" = "login", name?: string): Promise<PhoneOtpResult> => {
      try {
        // No retry: a duplicated request would invalidate the first code.
        await warmUpBackendWithin(15000);
        const body: Record<string, unknown> = { phone, purpose };
        if (name && name.trim()) body.name = name.trim();
        const data = await api<{
          status: string;
          message?: string;
          phone?: string;
          otp_length?: number;
          request_id?: string;
        }>("/api/auth/phone/request-otp", {
          method: "POST",
          body,
          timeoutMs: AUTH_TIMEOUT_MS,
        });
        return {
          success: true,
          message: data.message,
          otpLength: data.otp_length || 4,
          phone: data.phone,
          requestId: data.request_id,
        };
      } catch (e) {
        if (e instanceof ApiError) {
          const isProvider = isOtpProviderFailure(e.status, e.code);
          const isRateLimit = e.code === "cooldown" || e.status === 429;
          const isExpired = e.code === "expired";
          const isTooMany = e.code === "too_many_attempts";
          // Show the reason the server actually reported (unknown codes fall
          // back to its `message`) instead of always blaming configuration.
          const providerMessage = otpProviderErrorMessage(
            translate,
            e.status,
            e.code,
            e.message,
          );
          return {
            success: false,
            blocked: false,
            isProviderError: isProvider,
            retryAfter: e.retryAfter,
            error: isExpired
              ? translate("phoneAuth.errExpired")
              : isTooMany
              ? translate("phoneAuth.errTooManyAttempts")
              : isProvider
              ? providerMessage
              : isRateLimit
              ? e.message
              : e.message || translate("phoneAuth.errStart"),
          };
        }
        if (e instanceof NetworkError) {
          return {
            success: false,
            blocked: false,
            error: translate("phoneAuth.networkError"),
          };
        }
        return { success: false, error: extractError(e, translate("phoneAuth.errStart")) };
      }
    },
    [],
  );

  const verifyPhoneOtp = useCallback(
    async (phone: string, code: string, name?: string, requestId?: string): Promise<AuthResult> => {
      setIsLoading(true);
      try {
        const body: Record<string, unknown> = { phone, otp: code.trim() };
        if (requestId) body.request_id = requestId;
        if (name && name.trim()) body.name = name.trim();
        const data = await api<{ status: string; user?: Record<string, any>; message?: string }>(
          "/api/auth/phone/verify-otp",
          { method: "POST", body, timeoutMs: AUTH_TIMEOUT_MS },
        );
        if (data.user) {
          const u = toUser(data.user);
          await persist(u);
          return { success: true, user: u };
        }
        return { success: false, error: data.message || translate("errors.invalidOtp") };
      } catch (e) {
        if (e instanceof ApiError) {
          if (e.code === "expired") {
            return { success: false, error: translate("phoneAuth.errExpired") };
          }
          if (e.code === "too_many_attempts") {
            return { success: false, error: translate("phoneAuth.errTooManyAttempts") };
          }
          return { success: false, error: e.message || translate("phoneAuth.errVerify") };
        }
        if (e instanceof NetworkError) {
          return { success: false, error: translate("phoneAuth.networkError") };
        }
        return { success: false, error: extractError(e, translate("phoneAuth.errVerify")) };
      } finally {
        setIsLoading(false);
      }
    },
    [persist],
  );

  // 2. Registration OTP request.
  const requestRegistrationOtp = useCallback(
    async (name: string, email: string, password: string): Promise<MessageResult> => {
      try {
        // No retry here: a duplicate OTP request would invalidate the first
        // code. Instead wait briefly for the container to wake, then allow a
        // long single attempt.
        await warmUpBackendWithin(15000);
        const data = await api<{ status: string; message?: string }>("/api/register/request-otp", {
          method: "POST",
          body: { name: name.trim(), email: email.trim().toLowerCase(), password },
          timeoutMs: AUTH_TIMEOUT_MS,
        });
        return { success: true, message: data.message };
      } catch (e) {
        return { success: false, error: extractError(e, translate("errors.registerRequest")) };
      }
    },
    [],
  );

  // 3. Verify registration OTP.
  const verifyRegistrationOtp = useCallback(
    async (email: string, otp: string): Promise<AuthResult> => {
      try {
        const data = await api<{ status: string; user?: Record<string, any>; message?: string }>(
          "/api/register/verify-otp",
          {
            method: "POST",
            body: { email: email.trim().toLowerCase(), otp: otp.trim() },
            timeoutMs: AUTH_TIMEOUT_MS,
          },
        );
        if (data.user) {
          const u = toUser(data.user);
          await persist(u);
          return { success: true, user: u };
        }
        return { success: false, error: data.message || translate("errors.invalidOtp") };
      } catch (e) {
        return { success: false, error: extractError(e, translate("errors.verificationFailed")) };
      }
    },
    [persist],
  );

  // 4. Password reset OTP request.
  const requestPasswordResetOtp = useCallback(async (email: string): Promise<MessageResult> => {
    try {
    const data = await api<{ status: string; message?: string }>("/api/forgot-password/request-otp", {
      method: "POST",
      body: { email: email.trim().toLowerCase() },
      timeoutMs: AUTH_TIMEOUT_MS,
    });
      return { success: true, message: data.message };
    } catch (e) {
      return { success: false, error: extractError(e, translate("errors.resetDispatch")) };
    }
  }, []);

  // 5. Verify password reset OTP.
  const verifyPasswordResetOtp = useCallback(async (email: string, otp: string): Promise<MessageResult> => {
    try {
      const data = await api<{ status: string; message?: string }>("/api/forgot-password/verify-otp", {
        method: "POST",
        body: { email: email.trim().toLowerCase(), otp: otp.trim() },
        timeoutMs: AUTH_TIMEOUT_MS,
      });
      return { success: true, message: data.message };
    } catch (e) {
      return { success: false, error: extractError(e, translate("errors.resetVerify")) };
    }
  }, []);

  // 6. Reset password with verified OTP.
  const resetPassword = useCallback(
    async (email: string, otp: string, newPassword: string): Promise<MessageResult> => {
      try {
        const data = await api<{ status: string; message?: string }>("/api/forgot-password/reset", {
          method: "POST",
          body: { email: email.trim().toLowerCase(), otp: otp.trim(), newPassword },
          timeoutMs: AUTH_TIMEOUT_MS,
        });
        return { success: true, message: data.message };
      } catch (e) {
        return { success: false, error: extractError(e, translate("errors.passwordUpdate")) };
      }
    },
    [],
  );

  // 7. Guest preview login (5-minute limit).
  const loginAsGuest = useCallback(async (): Promise<AuthResult> => {
    setIsLoading(true);
    try {
      let data: { user?: Record<string, any> } | null = null;
      try {
        data = await api<{ user?: Record<string, any> }>("/api/guest-login", {
          method: "POST",
          timeoutMs: AUTH_TIMEOUT_MS,
        });
      } catch {
        // The web client falls back to a local guest session; keep identical behavior.
      }
      const guest: User = {
        id: data?.user?.id || 999999,
        username: data?.user?.username || "guest_preview",
        email: data?.user?.email || "guest@seediq.local",
        name: data?.user?.display_name || "Guest Preview",
        display_name: data?.user?.display_name || "Guest Preview",
        role: "Guest",
        isGuest: true,
        provider: "guest",
      };
      const expiresAt = Date.now() + GUEST_DURATION_SECONDS * 1000;
      await AsyncStorage.setItem(STORAGE_KEYS.guestExpiry, String(expiresAt));
      await persist(guest);
      setGuestTimeRemaining(GUEST_DURATION_SECONDS);
      return { success: true, user: guest };
    } finally {
      setIsLoading(false);
    }
  }, [persist]);

  const doLogoutInternal = useCallback(async () => {
    setUser(null);
    setGuestTimeRemaining(null);
    await clearStorage();
    try {
      await api("/api/logout", { method: "POST", timeoutMs: 5000 });
    } catch {
      // best-effort
    }
  }, [clearStorage]);

  // 8. Logout — clear local state instantly, notify servers in background.
  const logout = useCallback(async () => {
    const token = await AsyncStorage.getItem(STORAGE_KEYS.supabaseToken).catch(() => null);
    if (token) void supabaseAuth.signOut(token);
    setUser(null);
    setGuestTimeRemaining(null);
    await clearStorage();
    try {
      await api("/api/logout", { method: "POST", timeoutMs: 5000 });
    } catch {
      // best-effort
    }
  }, [clearStorage]);

  const refreshSession = useCallback(async (): Promise<boolean> => {
    try {
      const me = await api<{ authenticated: boolean; user?: Record<string, any> }>("/api/me", {
        timeoutMs: 6000,
      });
      return !!me.authenticated;
    } catch {
      return false;
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      isLoading,
      sessionRestored,
      guestTimeRemaining,
      formatGuestTime,
      signIn,
      requestPhoneOtp,
      verifyPhoneOtp,
      phoneAuthStatus,
      refreshPhoneAuthStatus,
      requestRegistrationOtp,
      verifyRegistrationOtp,
      requestPasswordResetOtp,
      verifyPasswordResetOtp,
      resetPassword,
      loginAsGuest,
      logout,
      refreshSession,
    }),
    [
      user,
      isLoading,
      sessionRestored,
      guestTimeRemaining,
      formatGuestTime,
      signIn,
      requestPhoneOtp,
      verifyPhoneOtp,
      phoneAuthStatus,
      refreshPhoneAuthStatus,
      requestRegistrationOtp,
      verifyRegistrationOtp,
      requestPasswordResetOtp,
      verifyPasswordResetOtp,
      resetPassword,
      loginAsGuest,
      logout,
      refreshSession,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function extractError(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof NetworkError) return e.message;
  return fallback;
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error(translate("errors.useAuthProvider"));
  return ctx;
}
