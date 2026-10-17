/**
 * SeedIQ Supabase Client (Zero-dependency Browser Client)
 * Integrates directly with Supabase GoTrue Auth and PostgREST API
 * for seamless client-side authentication and cloud persistence.
 */

export const SUPABASE_URL = (
  import.meta.env.VITE_SUPABASE_URL || "https://cqcdfvetexaqqcfogcds.supabase.co"
).replace(/\/$/, "");

export const SUPABASE_ANON_KEY = (
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  "sb_publishable_ysdQ2JVY5i7PY-plyOmh3w_ORe-Wr1e"
).trim();

const defaultHeaders = (token?: string) => ({
  "Content-Type": "application/json",
  apikey: SUPABASE_ANON_KEY,
  Authorization: `Bearer ${token || SUPABASE_ANON_KEY}`,
});

export const supabase = {
  url: SUPABASE_URL,
  anonKey: SUPABASE_ANON_KEY,

  auth: {
    /**
     * Sign in user with email & password via Supabase GoTrue
     */
    async signInWithPassword({ email, password }: { email: string; password: string }) {
      try {
        const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
          method: "POST",
          headers: defaultHeaders(),
          body: JSON.stringify({
            email: email.trim().toLowerCase(),
            password,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          const errMsg = data.error_description || data.msg || data.message || "Invalid email or password.";
          return { data: null, error: new Error(errMsg) };
        }
        return { data, error: null };
      } catch (err: any) {
        return { data: null, error: err };
      }
    },

    /**
     * Sign up user with email, password & metadata via Supabase GoTrue
     */
    async signUp({
      email,
      password,
      options,
    }: {
      email: string;
      password: string;
      options?: { data?: Record<string, any> };
    }) {
      try {
        const res = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
          method: "POST",
          headers: defaultHeaders(),
          body: JSON.stringify({
            email: email.trim().toLowerCase(),
            password,
            data: options?.data || {},
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          const errMsg = data.error_description || data.msg || data.message || "Registration failed.";
          return { data: null, error: new Error(errMsg) };
        }
        return { data, error: null };
      } catch (err: any) {
        return { data: null, error: err };
      }
    },

    /**
     * Sign out user from Supabase
     */
    async signOut(token?: string) {
      try {
        if (token) {
          await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
            method: "POST",
            headers: defaultHeaders(token),
          });
        }
      } catch {
        // Ignore network errors on logout
      }
    },

    /**
     * Retrieve authenticated user from token
     */
    async getUser(token: string) {
      try {
        const res = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
          method: "GET",
          headers: defaultHeaders(token),
        });
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    },
  },

  /**
   * PostgREST database table operations
   */
  from(table: string) {
    return {
      async insert(rows: Record<string, any> | Record<string, any>[], token?: string) {
        try {
          const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}`, {
            method: "POST",
            headers: {
              ...defaultHeaders(token),
              Prefer: "return=representation",
            },
            body: JSON.stringify(rows),
          });
          const data = await res.json();
          return { data, error: res.ok ? null : new Error(data.message || "Insert failed") };
        } catch (err: any) {
          return { data: null, error: err };
        }
      },

      async select(query = "*", token?: string) {
        try {
          const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}?select=${encodeURIComponent(query)}`, {
            method: "GET",
            headers: defaultHeaders(token),
          });
          const data = await res.json();
          return { data, error: res.ok ? null : new Error(data.message || "Select failed") };
        } catch (err: any) {
          return { data: null, error: err };
        }
      },
    };
  },
};
