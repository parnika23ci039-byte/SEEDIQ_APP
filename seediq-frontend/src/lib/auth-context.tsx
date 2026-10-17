import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from "react";
import { AuthTransitionOverlay, AuthTransitionState, AuthTransitionType } from "@/components/seediq/auth-transition-overlay";
import { supabase } from "@/lib/supabase";

export type UserRole = "Admin" | "Researcher" | "Farmer" | "Guest";

export interface User {
  id: string | number;
  username: string;
  email: string;
  name: string;
  display_name?: string;
  role: UserRole;
  avatar?: string;
  isGuest?: boolean;
  provider?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  guestTimeRemaining: number | null; // in seconds (300s = 5 mins max)
  formatGuestTime: (seconds: number | null) => string;
  signIn: (email: string, password: string) => Promise<{ success: boolean; user?: User; error?: string }>;
  requestRegistrationOtp: (name: string, email: string, password: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  verifyRegistrationOtp: (email: string, otp: string) => Promise<{ success: boolean; user?: User; error?: string }>;
  requestPasswordResetOtp: (email: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  verifyPasswordResetOtp: (email: string, otp: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  resetPassword: (email: string, otp: string, newPassword: string) => Promise<{ success: boolean; message?: string; error?: string }>;
  loginAsGuest: () => Promise<{ success: boolean; user?: User; error?: string }>;
  logout: () => Promise<void>;
  triggerLoginAnimation: (userName?: string, role?: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const STORAGE_KEY = "seediq_auth_user";
const GUEST_EXPIRY_KEY = "seediq_guest_expires_at";
const GUEST_DURATION_SECONDS = 300; // 5 Minutes maximum

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // ignore
    }
    return null;
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [guestTimeRemaining, setGuestTimeRemaining] = useState<number | null>(null);
  const [authTransition, setAuthTransition] = useState<AuthTransitionState>({
    type: null,
    message: "",
  });

  // Save or remove user in localStorage
  useEffect(() => {
    if (user) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(GUEST_EXPIRY_KEY);
    }
  }, [user]);

  // Sync session on mount with /api/me and Supabase
  useEffect(() => {
    const checkSession = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2500);
        const res = await fetch("/api/me", { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
          const data = await res.json();
          if (data.authenticated && data.user) {
            const isGuestRole = data.user.role === "Guest" || !!data.user.isGuest;
            
            // If it's a guest session, check expiry
            if (isGuestRole) {
              const savedExpiry = localStorage.getItem(GUEST_EXPIRY_KEY);
              if (savedExpiry) {
                const expiresAt = parseInt(savedExpiry, 10);
                const remaining = Math.floor((expiresAt - Date.now()) / 1000);
                if (remaining <= 0) {
                  // Expired already
                  logout();
                  return;
                }
              } else {
                // Initialize 5-minute expiry
                const expiresAt = Date.now() + GUEST_DURATION_SECONDS * 1000;
                localStorage.setItem(GUEST_EXPIRY_KEY, expiresAt.toString());
              }
            }

            const resolvedRole: UserRole =
              data.user.email?.toLowerCase() === "admin@seediq.ai" || data.user.username === "admin"
                ? "Admin"
                : data.user.email?.toLowerCase() === "researcher@quantum.org" || data.user.username === "researcher"
                ? "Researcher"
                : data.user.role || "Farmer";

            setUser({
              id: data.user.id,
              username: data.user.username,
              email: data.user.email,
              name: data.user.display_name || data.user.username,
              display_name: data.user.display_name || data.user.username,
              role: resolvedRole,
              isGuest: isGuestRole,
              provider: data.user.provider || "local",
            });
            return;
          }
        }
      } catch {
        // Backend /api/me unreachable (e.g. running on cloud host like Vercel)
      }

      // Check if there is an active Supabase cloud session token
      const supaToken = localStorage.getItem("seediq_supabase_token");
      if (supaToken) {
        try {
          const supaUser = await supabase.auth.getUser(supaToken);
          if (supaUser && supaUser.id) {
            const userEmail = (supaUser.email || "").toLowerCase();
            const resolvedRole: UserRole =
              userEmail === "admin@seediq.ai"
                ? "Admin"
                : userEmail === "researcher@quantum.org"
                ? "Researcher"
                : (supaUser.user_metadata?.role as UserRole) || "Farmer";

            setUser({
              id: supaUser.id,
              username: supaUser.user_metadata?.username || supaUser.email?.split("@")[0] || "user",
              email: supaUser.email || "",
              name: supaUser.user_metadata?.display_name || supaUser.user_metadata?.name || supaUser.email?.split("@")[0] || "User",
              display_name: supaUser.user_metadata?.display_name || supaUser.email?.split("@")[0],
              role: resolvedRole,
              isGuest: false,
              provider: "supabase",
            });
            return;
          }
        } catch {
          // Supabase token invalid or expired
        }
      }

      // If guest session in localStorage, check expiry
      const savedUserStr = localStorage.getItem(STORAGE_KEY);
      if (savedUserStr) {
        try {
          const savedUser = JSON.parse(savedUserStr);
          if (savedUser?.isGuest) {
            const savedExpiry = localStorage.getItem(GUEST_EXPIRY_KEY);
            if (savedExpiry) {
              const remaining = Math.floor((parseInt(savedExpiry, 10) - Date.now()) / 1000);
              if (remaining <= 0) {
                logout();
              }
            }
          }
        } catch {}
      }
    };
    checkSession();
  }, []);

  // --------------------------------------------------------------------------
  // Guest 5-Minute Maximum Countdown Timer Logic
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!user || (!user.isGuest && user.role !== "Guest")) {
      setGuestTimeRemaining(null);
      return;
    }

    // Get or initialize expiration timestamp
    let expiresAt: number;
    const saved = localStorage.getItem(GUEST_EXPIRY_KEY);
    if (saved) {
      expiresAt = parseInt(saved, 10);
    } else {
      expiresAt = Date.now() + GUEST_DURATION_SECONDS * 1000;
      localStorage.setItem(GUEST_EXPIRY_KEY, expiresAt.toString());
    }

    const updateTimer = () => {
      const now = Date.now();
      const diffSeconds = Math.max(0, Math.floor((expiresAt - now) / 1000));
      setGuestTimeRemaining(diffSeconds);

      if (diffSeconds <= 0) {
        // 5-minute timeout reached! Trigger auto-logout
        setAuthTransition({
          type: "guest_expire",
          message: "Guest session has expired (5-minute limit reached). Please sign in or register to continue.",
        });

        setTimeout(async () => {
          try {
            await fetch("/api/logout", { method: "POST" });
          } catch {}
          setUser(null);
          localStorage.removeItem(STORAGE_KEY);
          localStorage.removeItem(GUEST_EXPIRY_KEY);
          sessionStorage.clear();
          setAuthTransition({ type: null, message: "" });
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        }, 2200);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [user]);

  const formatGuestTime = (seconds: number | null): string => {
    if (seconds === null || seconds === undefined) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // --------------------------------------------------------------------------
  // Login / Verification Complete Animation Trigger
  // --------------------------------------------------------------------------
  const triggerLoginAnimation = useCallback(async (userName?: string, role?: string) => {
    setAuthTransition({
      type: "login",
      message: "Biometric & neural credentials synced. Initializing agricultural intelligence models...",
      userName: userName || "Researcher",
      userRole: role || "Farmer",
    });

    // Fast transition without long artificial delay
    await new Promise((res) => setTimeout(res, 250));
    setAuthTransition({ type: null, message: "" });
  }, []);

  // 1. Sign In with Email + Password (Hybrid Flask + Supabase Cloud Auth)
  const signIn = async (
    email: string,
    password: string
  ): Promise<{ success: boolean; user?: User; error?: string }> => {
    setIsLoading(true);
    try {
      const rawInput = email.trim().toLowerCase();
      const normalizedEmail =
        rawInput === "admin"
          ? "admin@seediq.ai"
          : rawInput === "researcher"
          ? "researcher@quantum.org"
          : rawInput;

      // First attempt: Backend Flask API (with Supabase sync)
      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: normalizedEmail,
            password: password,
          }),
        });

        if (res.ok) {
          const data = await res.json();
          if (data.status === "success" && data.user) {
            const backendUser = data.user;
            const userEmail = (backendUser.email || normalizedEmail).toLowerCase();
            const resolvedRole: UserRole =
              userEmail === "admin@seediq.ai" || backendUser.username === "admin"
                ? "Admin"
                : userEmail === "researcher@quantum.org" || backendUser.username === "researcher"
                ? "Researcher"
                : backendUser.role || "Farmer";

            const authenticatedUser: User = {
              id: backendUser.id,
              username: backendUser.username,
              email: backendUser.email || normalizedEmail,
              name: backendUser.display_name || backendUser.username,
              display_name: backendUser.display_name || backendUser.username,
              role: resolvedRole,
              isGuest: backendUser.role === "Guest",
              provider: backendUser.provider || "supabase",
            };

            localStorage.setItem(STORAGE_KEY, JSON.stringify(authenticatedUser));
            setUser(authenticatedUser);
            setIsLoading(false);
            await triggerLoginAnimation(authenticatedUser.name, authenticatedUser.role);
            return { success: true, user: authenticatedUser };
          } else if (data.status === "error") {
            setIsLoading(false);
            return { success: false, error: data.message || "Invalid email or password." };
          }
        }
      } catch {
        // Backend /api/login was unreachable (e.g. hosted on Vercel) -> Fallback directly to Supabase
      }

      // Direct Supabase GoTrue Auth Fallback (production cloud authentication)
      try {
        const { data: supaData, error: supaError } = await supabase.auth.signInWithPassword({
          email: normalizedEmail,
          password,
        });

        if (supaError) {
          setIsLoading(false);
          return { success: false, error: supaError.message || "Invalid email or password." };
        }

        if (supaData && (supaData.user || supaData.access_token)) {
          const supaUser = supaData.user || (supaData.access_token ? await supabase.auth.getUser(supaData.access_token) : null);
          const token = supaData.access_token || supaData.session?.access_token;
          if (token) {
            localStorage.setItem("seediq_supabase_token", token);
          }

          const username = supaUser?.user_metadata?.username || normalizedEmail.split("@")[0];
          const displayName = supaUser?.user_metadata?.display_name || supaUser?.user_metadata?.name || username;
          const resolvedRole: UserRole =
            normalizedEmail === "admin@seediq.ai" || username === "admin"
              ? "Admin"
              : normalizedEmail === "researcher@quantum.org" || username === "researcher"
              ? "Researcher"
              : (supaUser?.user_metadata?.role as UserRole) || "Farmer";

          const authenticatedUser: User = {
            id: supaUser?.id || `supa_${Date.now()}`,
            username: username,
            email: supaUser?.email || normalizedEmail,
            name: displayName,
            display_name: displayName,
            role: resolvedRole,
            isGuest: false,
            provider: "supabase",
          };

          localStorage.setItem(STORAGE_KEY, JSON.stringify(authenticatedUser));
          setUser(authenticatedUser);
          setIsLoading(false);
          await triggerLoginAnimation(authenticatedUser.name, authenticatedUser.role);
          return { success: true, user: authenticatedUser };
        }

        return { success: false, error: "Invalid email or password." };
      } catch (e: any) {
        return { success: false, error: e?.message || "Failed to reach authentication server." };
      }
    } finally {
      setIsLoading(false);
    }
  };

  // 2. Request OTP for Registration
  const requestRegistrationOtp = async (
    name: string,
    email: string,
    password: string
  ): Promise<{ success: boolean; message?: string; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/register/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim().toLowerCase(),
          password: password,
        }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "error") {
        return { success: false, error: data.message || "Failed to request registration code." };
      }

      return { success: true, message: data.message };
    } catch (e: any) {
      return { success: false, error: e?.message || "Failed to contact server." };
    } finally {
      setIsLoading(false);
    }
  };

  // 3. Verify OTP & Complete Registration
  const verifyRegistrationOtp = async (
    email: string,
    otp: string
  ): Promise<{ success: boolean; user?: User; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/register/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          otp: otp.trim(),
        }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "error") {
        return { success: false, error: data.message || "Invalid or expired verification code." };
      }

      const backendUser = data.user;
      const authenticatedUser: User = {
        id: backendUser.id,
        username: backendUser.username,
        email: backendUser.email,
        name: backendUser.display_name || backendUser.username,
        display_name: backendUser.display_name || backendUser.username,
        role: backendUser.role || "Farmer",
        isGuest: false,
        provider: "local",
      };

      setUser(authenticatedUser);
      // Trigger logged in animation on verification completion!
      await triggerLoginAnimation(authenticatedUser.name, authenticatedUser.role);
      return { success: true, user: authenticatedUser };
    } catch (e: any) {
      return { success: false, error: e?.message || "Verification failed." };
    } finally {
      setIsLoading(false);
    }
  };

  // 4. Request Password Reset OTP
  const requestPasswordResetOtp = async (
    email: string
  ): Promise<{ success: boolean; message?: string; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/forgot-password/request-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "error") {
        return { success: false, error: data.message || "Failed to dispatch reset code." };
      }

      return { success: true, message: data.message };
    } catch (e: any) {
      return { success: false, error: e?.message || "Failed to contact reset server." };
    } finally {
      setIsLoading(false);
    }
  };

  // 5. Verify Password Reset OTP
  const verifyPasswordResetOtp = async (
    email: string,
    otp: string
  ): Promise<{ success: boolean; message?: string; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/forgot-password/verify-otp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          otp: otp.trim(),
        }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "error") {
        return { success: false, error: data.message || "Invalid or expired code." };
      }

      return { success: true, message: data.message };
    } catch (e: any) {
      return { success: false, error: e?.message || "Code verification failed." };
    } finally {
      setIsLoading(false);
    }
  };

  // 6. Reset Password with verified OTP
  const resetPassword = async (
    email: string,
    otp: string,
    newPassword: string
  ): Promise<{ success: boolean; message?: string; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch("/api/forgot-password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          otp: otp.trim(),
          newPassword: newPassword,
        }),
      });
      const data = await res.json();

      if (!res.ok || data.status === "error") {
        return { success: false, error: data.message || "Failed to update password." };
      }

      return { success: true, message: data.message };
    } catch (e: any) {
      return { success: false, error: e?.message || "Password update failed." };
    } finally {
      setIsLoading(false);
    }
  };

  // 7. Guest Mode with 5-minute expiration
  const loginAsGuest = async (): Promise<{ success: boolean; user?: User; error?: string }> => {
    setIsLoading(true);
    try {
      const expiresAt = Date.now() + GUEST_DURATION_SECONDS * 1000;
      localStorage.setItem(GUEST_EXPIRY_KEY, expiresAt.toString());

      const res = await fetch("/api/guest-login", { method: "POST" });
      const data = await res.json();

      const guestUser: User = {
        id: data.user?.id || 999999,
        username: data.user?.username || "guest_preview",
        email: data.user?.email || "guest@seediq.local",
        name: data.user?.display_name || "Guest Preview",
        display_name: data.user?.display_name || "Guest Preview",
        role: "Guest",
        isGuest: true,
        provider: "guest",
      };

      setUser(guestUser);
      setGuestTimeRemaining(GUEST_DURATION_SECONDS);
      await triggerLoginAnimation("Guest Explorer (5-Min Preview)", "Guest");
      return { success: true, user: guestUser };
    } catch (e: any) {
      const fallbackGuest: User = {
        id: 999999,
        username: "guest_preview",
        email: "guest@seediq.local",
        name: "Guest Preview",
        display_name: "Guest Preview",
        role: "Guest",
        isGuest: true,
        provider: "guest",
      };
      setUser(fallbackGuest);
      setGuestTimeRemaining(GUEST_DURATION_SECONDS);
      await triggerLoginAnimation("Guest Explorer (5-Min Preview)", "Guest");
      return { success: true, user: fallbackGuest };
    } finally {
      setIsLoading(false);
    }
  };

  // 8. Instant Logout with Zero Latency
  const logout = async () => {
    // 1. Immediately clear user state & local storage in 0ms
    setUser(null);
    setGuestTimeRemaining(null);
    setAuthTransition({ type: null, message: "" });

    if (typeof window !== "undefined") {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(GUEST_EXPIRY_KEY);
      localStorage.removeItem("seediq_supabase_token");
      sessionStorage.clear();
    }

    // 2. Fire and forget remote sessions in the background without blocking UI
    try {
      supabase.auth.signOut().catch(() => {});
      fetch("/api/logout", { method: "POST" }).catch(() => {});
    } catch {}

    // 3. Instant navigation to login
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        guestTimeRemaining,
        formatGuestTime,
        signIn,
        requestRegistrationOtp,
        verifyRegistrationOtp,
        requestPasswordResetOtp,
        verifyPasswordResetOtp,
        resetPassword,
        loginAsGuest,
        logout,
        triggerLoginAnimation,
      }}
    >
      <AuthTransitionOverlay transition={authTransition} />
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
