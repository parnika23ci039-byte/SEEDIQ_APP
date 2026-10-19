// Central environment configuration for the SeedIQ mobile app.
//
// DEFAULT: the deployed SeedIQ Flask backend (Railway, v4.3). The backend is
// the source of truth for every prediction, so a packaged APK must target it
// by default — a client-installed build cannot depend on a dev machine.
//
// LOCAL DEV: point at your local Flask server instead, e.g.
// Android emulator: http://10.0.2.2:5000 (host loopback).
// Physical device: your LAN IP, e.g. http://192.168.1.20:5000.
//
// Set EXPO_PUBLIC_API_BASE_URL to override without editing code.

const envUrl = process.env.EXPO_PUBLIC_API_BASE_URL;

export const API_BASE_URL: string =
  envUrl && envUrl.trim().length > 0
    ? envUrl.trim().replace(/\/$/, "")
    : "https://sublime-ambition-production-488f.up.railway.app";

// Supabase project used by the web client for cloud auth fallback.
export const SUPABASE_URL = "https://cqcdfvetexaqqcfogcds.supabase.co";
export const SUPABASE_ANON_KEY = "sb_publishable_ysdQ2JVY5i7PY-plyOmh3w_ORe-Wr1e";

export const STORAGE_KEYS = {
  user: "seediq_auth_user",
  guestExpiry: "seediq_guest_expires_at",
  supabaseToken: "seediq_supabase_token",
} as const;

// Guest sessions mirror the web client: hard 5-minute preview.
export const GUEST_DURATION_SECONDS = 300;

export const APP_NAME = "SeedIQ";
export const APP_TAGLINE = "Hybrid AI × Quantum Intelligence";
