# attic — files intentionally kept out of the Expo bundle

## `signin.nextjs.tsx`

**Status:** preserved, not bundled. Moved out of `app/(auth)/signin.tsx` on 2026-10-12.

**Provenance:** added 2026-10-11 19:37 — *after* the last successful APK build
(2026-10-09 07:37) — so it was never part of a working release.

**Why it cannot live in the route tree:** the file is a **Next.js / React Hook
Form** component, not a React Native one. It imports `next/navigation`,
`react-hook-form` and `@hookform/resolvers/zod`, plus `@/lib/auth-schema`,
`@/lib/auth-storage`, `@/components/ui/button`, `@/components/ui/input` and
`@/components/ui/form-error`. None of those packages are installed
(`next`, `react-hook-form`, `@hookform` are absent from `node_modules`) and none
of those `@/…` modules exist — `@/*` maps to `./src/*` in this app, and no such
files are present. Nothing in `app/` or `src/` links to a `/signin` route, and
the file exports no default (expo-router requires one), so it could never render.

**Reproduced failure** (`npx expo export --platform android`, exit 1):

```
Error: Unable to resolve module next/navigation from
  /Users/apple/SeedIQ/seediq-mobile/app/(auth)/signin.tsx
Import stack: app/(auth)/signin.tsx | import "next/navigation"
             app (require.context)
```

Because expo-router indexes every file under `app/`, the unresolvable import
broke the **entire** JavaScript bundle — i.e. no release APK could be produced.

**The real mobile sign-in** is `app/(auth)/login.tsx` (phone-first, 4-digit OTP,
email fallback). It is untouched and is what the app actually routes to.

**To revive this file:** it needs `next`, `react-hook-form`,
`@hookform/resolvers` and the missing `@/lib/*` + `@/components/ui/*` modules,
so it belongs in a Next.js project, not here. Bytes are unchanged
(`sha256 d4e0563b1623b4f8c6e77b4df3a3bfce692bf6b6cd6fee914943cd5d836cdc72`).
