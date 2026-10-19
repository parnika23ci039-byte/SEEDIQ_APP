# SeedIQ Android (React Native / Expo)

Native Android client for the SeedIQ hybrid AI + quantum agriculture platform. This is a **new mobile client** — it does not modify, replace, or depend on changes to the existing web frontend (`seediq-frontend/`) or Flask backend (`SeedIQ/`). Both remain fully intact and functional.

## Stack

- **Expo SDK 54** / React Native 0.81 / TypeScript (strict)
- **expo-router** file-based navigation (auth stack + bottom tabs + detail stacks)
- **TanStack React Query** for data caching and retry
- Minimal light theme: one green accent, neutral surfaces, no decorative noise

## Project layout

```
seediq-mobile/
├── app/                    # expo-router routes
│   ├── _layout.tsx         # providers + stack registration
│   ├── index.tsx           # splash redirect (session-aware)
│   ├── (auth)/             # login, register (2-step OTP), forgot-password (3-step)
│   ├── (tabs)/             # home, tools, data, alerts, profile, admin (hidden tab)
│   ├── crop-ai.tsx         # AI module stack screens
│   ├── yield-ai.tsx
│   ├── seed-ai.tsx
│   ├── storage-ai.tsx
│   ├── quantum.tsx
│   ├── upload.tsx          # CSV dataset ingestion (role-gated)
│   └── district/[id].tsx   # district storage detail
├── src/
│   ├── lib/
│   │   ├── config.ts       # API base URL + storage keys (env-overridable)
│   │   ├── api.ts          # centralized fetch client (credentials, timeouts, typed errors)
│   │   ├── auth-context.tsx# session state, OTP flows, guest 5-min timer, logout
│   │   ├── supabase.ts     # GoTrue fallback auth (mirrors web client)
│   │   ├── hooks.ts        # React Query hooks + live Open-Meteo weather
│   │   └── types.ts        # response types mirroring the Flask backend
│   ├── components/         # ui.tsx primitives, ai-screen shell, brand
│   └── theme/theme.ts      # design tokens
└── app.json                # Android package ai.seediq.mobile, permissions
```

## Backend integration map

Every screen talks to the existing Flask backend — no mock data anywhere.

| Mobile screen | Endpoint(s) |
|---|---|
| Login | `POST /api/login` (cookie session) → Supabase GoTrue fallback |
| Register (OTP) | `POST /api/register/request-otp`, `/api/register/verify-otp` |
| Forgot password | `POST /api/forgot-password/request-otp`, `/verify-otp`, `/reset` |
| Guest preview | `POST /api/guest-login` + 5-minute local countdown (auto-logout) |
| Home dashboard | `GET /api/dashboard`, `GET /api/me`, Open-Meteo weather (same public API as web) |
| Crop AI | `POST /api/crop-recommendation` (sliders → soil analysis, growth plan, disease advisory) |
| Yield AI | `POST /api/yield-prediction` (crop/season/area → t/ha + market analysis) |
| Seed AI | `POST /api/seed-viability` (moisture/weight → Viable/Non-Viable) |
| Storage AI | `POST /api/storage-recommendation` (crop → protocol from `knowledge_base/storage_db.json`) |
| Quantum ML | `POST /api/quantum-ml` (multipart form → meta-model success probability) |
| Alerts tab | `GET /api/notifications/district-storage?limit=21`, `GET /api/districts/storage-live` |
| Data tab | `GET /api/datasets` |
| Upload | `POST /api/datasets/upload` (CSV ≤10 MB, Admin/Researcher only — enforced server-side too) |
| Profile | `GET /api/health`, `POST /api/logout` |
| Admin console | `GET /api/admin/users`, `GET /api/admin/activity-logs`, `POST /api/retrain` (Admin only) |

## Running the app

### 1. Start the SeedIQ backend

```bash
# from the repository root
pip install -r requirements.txt   # Flask, pandas, scikit-learn, xgboost, flask-cors, python-dotenv...
python SeedIQ/app.py              # serves on 0.0.0.0:5000
```

The backend already sends `CORS(app, supports_credentials=True)`, so cookie sessions work from the device/emulator.

### 2. Point the app at the backend

The default base URL is the Android-emulator host alias:

```
http://10.0.2.2:5000
```

- **Android emulator** — works as-is (10.0.2.2 = host loopback).
- **Physical device** — set your computer's LAN IP when starting:

  ```bash
  EXPO_PUBLIC_API_BASE_URL=http://192.168.1.20:5000 npx expo start
  ```

  (Also make sure the phone and computer share the network and the Flask dev server binds 0.0.0.0 — it does by default.)
- **Production** — point at the deployed Render service:

  ```bash
  EXPO_PUBLIC_API_BASE_URL=https://your-seediq-api.onrender.com npx expo start
  ```

### 3. Start the dev client

```bash
cd seediq-mobile
npx expo start          # press "a" for Android emulator, or scan the QR with Expo Go
```

### 4. Production Android build

```bash
npx expo run:android                          # debug build on a connected device/emulator
# or
eas build -p android --profile preview        # APK via EAS (requires an Expo account)
```

## Demo accounts (pre-provisioned in the backend)

| Role | Email | Password |
|---|---|---|
| Admin | admin@seediq.ai | admin123 |
| Researcher | researcher@quantum.org | research123 |

Admin/Researcher unlock dataset upload and the Admin console; normal registered accounts are Farmers.

## Design notes

- **Navigation** — bottom tabs (Home / AI Tools / Data / Alerts / Profile) for the primary surfaces; stack screens for the five AI modules, district detail, upload, and admin. Admin is deliberately outside the tab bar and role-gated.
- **Guest mode** — mirrors the web client: hard 5-minute preview with a visible countdown and automatic logout.
- **AI results** — show the ensemble verdict plus classical/quantum sub-model outputs exactly as the backend returns them, with model disagreement surfaced honestly (e.g. "Models disagree").
- **Errors** — every API screen has loading / error+retry / empty states; auth expiry and 403 role errors surface their real backend messages.
- **Back navigation** — Android hardware back works via expo-router stacks; AI screens fall back to the AI Tools tab when no history exists.
