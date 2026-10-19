// Central design system for the SeedIQ Android app.
//
// PALETTE — the client's final brand palette. Applied consistently to every
// surface, and mirrored one-for-one in the native Android resources
// (res/values/colors.xml, styles.xml) and in app.json so the splash, the
// launcher icon and the in-app UI can never drift apart.
//
//   FOREST  #0B2B26  → darkest: navigation, headers, primary text
//   PINE    #163832  → deep green: secondary headers, dark controls
//   TEAL    #235347  → middle green: AI cards, Quantum Labs, interactive controls
//   SAGE    #8EB698  → light green: borders, secondary text, tints
//   MINT    #DAF1DE  → light mint: background, surfaces, cards, selected states
//
// Supporting shades are mixed from those five hues so the app reads as one
// coherent brand instead of a grab-bag of colours.

export const palette = {
  forest: "#0B2B26",
  pine: "#163832",
  teal: "#235347",
  sage: "#8EB698",
  mint: "#DAF1DE",
} as const;

export const theme = {
  palette,
  colors: {
    // Surfaces
    background: palette.mint,
    surface: "#F3FBF5",
    surfaceMuted: "#C8E6D1",
    border: "#B4D9C0",
    borderStrong: palette.sage,

    // Type
    text: palette.forest,
    textSecondary: palette.teal,
    textMuted: "#4C7A69",
    textInverse: palette.mint,

    // Brand
    primary: palette.teal,
    primaryDark: palette.forest,
    primarySoft: "#CCE7D5",
    primaryBorder: palette.sage,

    // Navigation (darkest green bar, light mint accents)
    navBackground: palette.forest,
    navActive: palette.mint,
    navInactive: palette.sage,
    navBorder: palette.pine,

    // Deep-green feature surfaces (Quantum Labs, hero panels)
    feature: palette.pine,
    featureSoft: "#D7ECE0",
    accent: palette.sage,

    // Direct accessors for the five brand hues, so a screen can name the exact
    // palette entry it means instead of borrowing a semantic alias.
    forest: palette.forest,
    pine: palette.pine,
    teal: palette.teal,
    sage: palette.sage,
    mint: palette.mint,

    danger: "#A33A22",
    dangerSoft: "#FBE6DF",
    warning: "#8A6A12",
    warningSoft: "#FAF0D6",
    success: "#2F6B45",
    successSoft: "#DCF0E2",
    info: palette.teal,
    infoSoft: "#D8EAE3",

    // District risk palette (semantic risk levels from the backend)
    riskCritical: "#A33A22",
    riskCriticalSoft: "#FBE6DF",
    riskWarning: "#8A6A12",
    riskWarningSoft: "#FAF0D6",
    riskMonitor: "#2F6B5C",
    riskMonitorSoft: "#D8EAE3",
    riskStable: "#2F6B45",
    riskStableSoft: "#DCF0E2",

    overlay: "rgba(11, 43, 38, 0.5)",
    skeleton: "#C9E5D2",
  },
  spacing: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    xxl: 28,
  },
  radii: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 22,
    full: 999,
  },
  typography: {
    title: { fontSize: 24, fontWeight: "700" as const, color: palette.forest },
    heading: { fontSize: 18, fontWeight: "700" as const, color: palette.forest },
    subheading: { fontSize: 15, fontWeight: "600" as const, color: palette.forest },
    body: { fontSize: 14, fontWeight: "400" as const, color: palette.teal },
    caption: { fontSize: 12, fontWeight: "400" as const, color: "#4C7A69" },
    label: { fontSize: 13, fontWeight: "600" as const, color: palette.forest },
    metric: { fontSize: 28, fontWeight: "700" as const, color: palette.forest },
  },
  shadows: {
    card: {
      shadowColor: palette.forest,
      shadowOpacity: 0.07,
      shadowRadius: 8,
      shadowOffset: { width: 0, height: 2 },
      elevation: 2,
    },
    fab: {
      shadowColor: palette.forest,
      shadowOpacity: 0.2,
      shadowRadius: 10,
      shadowOffset: { width: 0, height: 4 },
      elevation: 6,
    },
  },
} as const;

export type Theme = typeof theme;
