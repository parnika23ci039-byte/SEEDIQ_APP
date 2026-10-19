import React from "react";
import { Image, Pressable, StyleSheet, Text, View, StyleProp, ViewStyle } from "react-native";
import { theme } from "../theme/theme";
import { useI18n } from "../i18n";

// Original SeedIQ auth artwork, reused from seediq-frontend/public/auth_quantum_farm.jpg
const AUTH_HERO = require("../../assets/brand/auth_quantum_farm.jpg");
// The real SeedIQ brand artwork: the same asset the Launcher icon is generated
// from (client banner artwork — the sprout with the quantum-circuit backdrop).
// One mark everywhere: launcher, auth header, hero, dashboard, About.
const BRAND_LOGO = require("../../assets/icon.png");

/**
 * The client's SeedIQ brand mark as a self-contained tile.
 * Rendered with rounded corners so it sits cleanly on any surface.
 */
export function BrandLogo({ width = 96, radius = 16 }: { width?: number; radius?: number }) {
  // The brand artwork is square (1024x1024), so the tile stays square too.
  return (
    <Image
      source={BRAND_LOGO}
      style={{ width, height: width, borderRadius: radius, backgroundColor: theme.colors.navBackground }}
      resizeMode="cover"
      accessibilityLabel="SeedIQ"
    />
  );
}

export function Logo({ size = 40, showTagline = true }: { size?: number; showTagline?: boolean }) {
  const { t } = useI18n();
  return (
    <View style={styles.logoRow}>
      {/* The real SeedIQ brand mark — same artwork as the Launcher icon. The old
          "quantum architecture" symbol is no longer used anywhere in the app. */}
      <BrandLogo width={size} radius={Math.round(size * 0.22)} />
      <View>
        <Text style={[styles.logoText, { fontSize: size * 0.55 }]}>
          Seed<Text style={{ color: theme.colors.primary }}>IQ</Text>
        </Text>
        {showTagline && <Text style={styles.logoTagline}>{t("app.tagline")}</Text>}
      </View>
    </View>
  );
}

export function AuthHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <View style={styles.authHeader}>
      {/* Original SeedIQ auth hero image (same asset the web login/register pages use)
          with the client-supplied logo tile anchored on top of it. */}
      <View style={styles.authHeroWrap}>
        <Image source={AUTH_HERO} style={styles.authHero} resizeMode="cover" />
        <View style={styles.authHeroScrim} />
        <View style={styles.authHeroBadge}>
          <BrandLogo width={68} radius={12} />
        </View>
      </View>
      <Logo />
      <Text style={styles.authTitle}>{title}</Text>
      {subtitle ? <Text style={styles.authSubtitle}>{subtitle}</Text> : null}
    </View>
  );
}

export function BackLink({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={8}>
      <Text style={styles.backLink}>{label}</Text>
    </Pressable>
  );
}

export function FooterLink({ prompt, action, onPress }: { prompt: string; action: string; onPress: () => void }) {
  return (
    <View style={styles.footerRow}>
      <Text style={styles.footerPrompt}>{prompt} </Text>
      <Pressable onPress={onPress} hitSlop={8}>
        <Text style={styles.footerAction}>{action}</Text>
      </Pressable>
    </View>
  );
}

export function GuestBanner({ seconds }: { seconds: string }) {
  const { t } = useI18n();
  return (
    <View style={styles.guestBanner}>
      <Text style={styles.guestBannerText}>{t("session.guestBanner", { time: seconds })}</Text>
    </View>
  );
}

export function FormError({ message }: { message: string }) {
  if (!message) return null;
  return (
    <View style={styles.formError}>
      <Text style={styles.formErrorText}>{message}</Text>
    </View>
  );
}

export function FormSuccess({ message }: { message: string }) {
  if (!message) return null;
  return (
    <View style={styles.formSuccess}>
      <Text style={styles.formSuccessText}>{message}</Text>
    </View>
  );
}

export function ScreenCenter({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.screenCenter, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  logoRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  logoBox: {
    backgroundColor: theme.colors.primarySoft,
    borderWidth: 1,
    borderColor: theme.colors.primaryBorder,
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: { fontWeight: "800", color: theme.colors.text, letterSpacing: 0.2 },
  logoTagline: {
    fontSize: 9,
    fontWeight: "600",
    letterSpacing: 1.4,
    color: theme.colors.textMuted,
    marginTop: 1,
  },
  authHeader: { gap: 12, marginBottom: 8 },
  authHeroWrap: {
    width: "100%",
    height: 156,
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    backgroundColor: theme.colors.navBackground,
  },
  authHero: { width: "100%", height: "100%" },
  authHeroScrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(40, 54, 24, 0.22)",
  },
  authHeroBadge: { position: "absolute", left: 14, bottom: 14 },
  authHeroImage: {
    width: "100%",
    height: 120,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.surfaceMuted,
  },
  authTitle: { fontSize: 24, fontWeight: "800", color: theme.colors.text, marginTop: 8 },
  authSubtitle: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 20 },
  backLink: { color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  footerRow: { flexDirection: "row", justifyContent: "center", alignItems: "center", marginTop: 4 },
  footerPrompt: { color: theme.colors.textSecondary, fontSize: 13 },
  footerAction: { color: theme.colors.primary, fontWeight: "700", fontSize: 13 },
  guestBanner: {
    backgroundColor: theme.colors.warningSoft,
    borderColor: theme.colors.borderStrong,
    borderWidth: 1,
    borderRadius: theme.radii.md,
    paddingVertical: 10,
    paddingHorizontal: theme.spacing.md,
  },
  guestBannerText: { color: theme.colors.warning, fontWeight: "600", fontSize: 13, textAlign: "center" },
  formError: {
    backgroundColor: theme.colors.dangerSoft,
    borderColor: theme.colors.dangerSoft,
    borderWidth: 1,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
  },
  formErrorText: { color: theme.colors.danger, fontSize: 13, lineHeight: 18 },
  formSuccess: {
    backgroundColor: theme.colors.successSoft,
    borderColor: theme.colors.primaryBorder,
    borderWidth: 1,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
  },
  formSuccessText: { color: theme.colors.success, fontSize: 13, lineHeight: 18 },
  screenCenter: { flex: 1, justifyContent: "center" },
});
