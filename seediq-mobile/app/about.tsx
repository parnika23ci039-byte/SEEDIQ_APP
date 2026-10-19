import React from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useVideoPlayer, VideoView } from "expo-video";
import { ChevronLeft } from "lucide-react-native";
import { Screen, Card, Button } from "@/components/ui";
import { BrandLogo } from "@/components/brand";
import { theme } from "@/theme/theme";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { STATUS_BAR_TOP } from "@/lib/layout";

// Original SeedIQ landing assets, reused verbatim:
//   seediq-frontend/public/karnataka_panoramic_landscape.jpg
//   seediq-frontend/public/intro_plant.mp4
const PANORAMA = require("../assets/brand/karnataka_panoramic_landscape.jpg");
const INTRO_VIDEO = require("../assets/brand/intro_plant.mp4");

/**
 * Reproduces the content of the web landing hero (index.tsx) on Android:
 * same brand copy, the original panoramic landscape, and the cinematic intro
 * plant video. The web page's particle canvas / parallax marketing sections are
 * intentionally not carried over (see PARITY.md) — only the hero content is.
 */
export default function AboutScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { user } = useAuth();

  const player = useVideoPlayer(INTRO_VIDEO, (p) => {
    p.loop = true;
    p.muted = true;
    p.play();
  });

  const go = () => router.replace(user ? "/(tabs)/home" : "/(auth)/login");

  return (
    // The app draws edge-to-edge, so the first row must clear the system status
    // bar or its Back control sits under it and the system swallows the taps.
    <Screen style={{ paddingTop: STATUS_BAR_TOP }}>
      <View style={styles.headerRow}>
        <Pressable
          // Opened before login there is nothing to go back to, so fall back to
          // the auth entry point instead of the protected tab route.
          onPress={() =>
            router.canGoBack()
              ? router.back()
              : router.replace(user ? "/(tabs)/profile" : "/(auth)/login")
          }
          hitSlop={12}
          style={styles.backBox}
        >
          <ChevronLeft size={22} color={theme.colors.text} />
          <Text style={styles.backText}>{t("common.back")}</Text>
        </Pressable>
      </View>

      {/* Brand lock-up — same mark, name and tagline as the web hero */}
      <View style={styles.brandRow}>
        {/* Client-supplied SeedIQ logo. */}
        <BrandLogo width={64} radius={14} />
        <View style={{ flex: 1 }}>
          <Text style={styles.brandName}>
            SEED<Text style={{ color: theme.colors.primary }}>IQ</Text>
          </Text>
          <Text style={styles.brandTagline}>{t("app.taglineLong")}</Text>
        </View>
      </View>

      <Image source={PANORAMA} style={styles.panorama} resizeMode="cover" />

      <Card>
        <Text style={styles.h2}>{t("about.heading")}</Text>
        <Text style={styles.paragraph}>{t("about.paragraph")}</Text>
        <Button
          label={user ? t("common.goToDashboard") : t("common.getStarted")}
          onPress={go}
          style={{ marginTop: theme.spacing.sm }}
        />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("about.introduction")}</Text>
        <View style={styles.videoWrap}>
          <VideoView player={player} style={styles.video} nativeControls contentFit="cover" />
        </View>
        <Text style={styles.caption}>{t("about.videoCaption")}</Text>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center" },
  backBox: { flexDirection: "row", alignItems: "center", gap: 2 },
  backText: { fontSize: 14, color: theme.colors.text, fontWeight: "600" },
  brandRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  brandName: { fontSize: 24, fontWeight: "800", color: theme.colors.text, letterSpacing: 0.5 },
  brandTagline: { fontSize: 10, fontWeight: "700", letterSpacing: 1.2, color: theme.colors.textMuted, marginTop: 2 },
  panorama: {
    width: "100%",
    height: 170,
    borderRadius: theme.radii.lg,
    backgroundColor: theme.colors.surfaceMuted,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  h2: { fontSize: 18, fontWeight: "700", color: theme.colors.text, lineHeight: 24 },
  paragraph: { fontSize: 14, color: theme.colors.textSecondary, lineHeight: 21, marginTop: theme.spacing.sm },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: theme.spacing.sm },
  videoWrap: { borderRadius: theme.radii.md, overflow: "hidden", backgroundColor: "#000" },
  video: { width: "100%", height: 190 },
  caption: { fontSize: 12, color: theme.colors.textMuted, marginTop: theme.spacing.sm },
});
