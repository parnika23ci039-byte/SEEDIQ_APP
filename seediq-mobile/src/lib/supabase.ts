import { SUPABASE_ANON_KEY, SUPABASE_URL } from "./config";

/**
 * Minimal Supabase GoTrue client for cloud-auth fallback.
 * Mirrors the zero-dependency client used by the web frontend.
 */

const headers = (token?: string) => ({
  "Content-Type": "application/json",
  apikey: SUPABASE_ANON_KEY,
  Authorization: `Bearer ${token || SUPABASE_ANON_KEY}`,
});

export interface SupabaseAuthUser {
  id: string;
  email?: string;
  user_metadata?: {
    username?: string;
    display_name?: string;
    name?: string;
    role?: string;
  };
}

export interface SupabaseSignInResult {
  data: { user: SupabaseAuthUser; access_token?: string } | null;
  error: Error | null;
}

export const supabaseAuth = {
  async signInWithPassword(email: string, password: string): Promise<SupabaseSignInResult> {
    try {
      const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.error_description || data.msg || data.message || "Invalid email or password.";
        return { data: null, error: new Error(msg) };
      }
      return {
        data: {
          user: data.user as SupabaseAuthUser,
          access_token: data.access_token as string | undefined,
        },
        error: null,
      };
    } catch (err: any) {
      return { data: null, error: err instanceof Error ? err : new Error(String(err)) };
    }
  },

  async getUser(token: string): Promise<SupabaseAuthUser | null> {
    try {
      const res = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
        method: "GET",
        headers: headers(token),
      });
      if (!res.ok) return null;
      return (await res.json()) as SupabaseAuthUser;
    } catch {
      return null;
    }
  },

  async signOut(token?: string): Promise<void> {
    try {
      if (token) {
        await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
          method: "POST",
          headers: headers(token),
        });
      }
    } catch {
      // Ignore network errors on logout
    }
  },
};
