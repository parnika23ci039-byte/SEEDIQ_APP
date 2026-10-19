import React, { useState } from "react";
import { Image, Share, Text, View, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Share as ShareIcon, FileText } from "lucide-react-native";
import { Screen, Button, ErrorBanner, Card } from "./ui";
import { theme } from "../theme/theme";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { shareReportPdf, type ReportData } from "@/lib/report";

// Original SeedIQ farm artwork (the same asset the web auth pages use), reused
// as the module banner so every AI screen opens on real agricultural imagery.
const MODULE_BANNER = require("../../assets/brand/auth_quantum_farm.jpg");

/**
 * Shared scaffold for all AI module screens:
 * - back header
 * - input section inside a card
 * - predict button with loading
 * - error banner with retry
 * - result slot
 * - share action (real result text only)
 * - PDF report action (expo-print → Android share sheet)
 */
export function AiScreenShell({
  title,
  subtitle,
  children,
  result,
  error,
  isPredicting,
  onPredict,
  onRetry,
  shareText,
  reportData,
  predictLabel,
  hidePredict = false,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  result: React.ReactNode | null;
  error: string | null;
  isPredicting: boolean;
  onPredict: () => void;
  onRetry?: () => void;
  shareText?: string | null;
  reportData?: ReportData | null;
  predictLabel?: string;
  hidePredict?: boolean;
}) {
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const handleShare = async () => {
    if (!shareText) return;
    try {
      await Share.share({ message: shareText });
    } catch {
      // user cancelled or share unavailable — non-fatal
    }
  };

  const handleReport = async () => {
    if (!reportData) return;
    setIsGeneratingReport(true);
    setReportError(null);
    try {
      const outcome = await shareReportPdf(reportData, user?.display_name || user?.name);
      if (outcome === "unavailable") {
        setReportError(t("aiScreen.pdfUnavailable"));
      }
    } catch (e: any) {
      // Sharing dismissed by the user is non-fatal; real failures show a message.
      if (e?.message) setReportError(e.message);
    } finally {
      setIsGeneratingReport(false);
    }
  };

  return (
    <Screen>
      <View style={styles.headerRow}>
        <BackButton
          onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/tools"))}
        />
      </View>
      <View style={styles.banner}>
        <Image source={MODULE_BANNER} style={styles.bannerImage} resizeMode="cover" />
        <View style={styles.bannerScrim} />
        <Text style={styles.bannerTitle}>{title}</Text>
      </View>
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}

      <Card>
        {children}
        {!hidePredict && (
          <Button
            label={predictLabel ?? t("aiScreen.predictDefault")}
            onPress={onPredict}
            loading={isPredicting}
            style={{ marginTop: theme.spacing.md }}
          />
        )}
      </Card>

      {error ? <ErrorBanner message={error} onRetry={onRetry} /> : null}

      {result}

      {reportData && result ? (
        <Button
          label={isGeneratingReport ? t("aiScreen.preparingPdf") : t("aiScreen.getPdf")}
          icon={<FileText size={16} color={theme.colors.primary} />}
          onPress={handleReport}
          loading={isGeneratingReport}
        />
      ) : null}

      {shareText && result ? (
        <Button
          label={t("aiScreen.shareResult")}
          variant="outline"
          icon={<ShareIcon size={16} color={theme.colors.primary} />}
          onPress={handleShare}
        />
      ) : null}

      {reportError ? <Text style={styles.reportError}>{reportError}</Text> : null}
    </Screen>
  );
}

export function BackButton({ onPress }: { onPress: () => void }) {
  const { t } = useI18n();
  return (
    <View style={styles.backBox}>
      <ChevronLeft size={22} color={theme.colors.text} onPress={onPress} hitSlop={12} />
      <Text onPress={onPress} style={styles.backText}>
        {t("common.back")}
      </Text>
    </View>
  );
}

export function ResultHeading({ children }: { children: React.ReactNode }) {
  return <Text style={styles.resultHeading}>{children}</Text>;
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", marginBottom: 2 },
  backBox: { flexDirection: "row", alignItems: "center", gap: 2 },
  backText: { fontSize: 14, color: theme.colors.text, fontWeight: "600" },
  banner: {
    height: 104,
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    backgroundColor: theme.colors.navBackground,
    justifyContent: "flex-end",
    marginTop: theme.spacing.sm,
  },
  bannerImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  bannerScrim: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(40, 54, 24, 0.5)" },
  bannerTitle: {
    fontSize: 22,
    fontWeight: "800",
    color: theme.palette.mint,
    padding: theme.spacing.md,
  },
  title: { fontSize: 22, fontWeight: "800", color: theme.colors.text, marginTop: theme.spacing.sm },
  subtitle: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19, marginTop: 4 },
  resultHeading: {
    fontSize: 17,
    fontWeight: "700",
    color: theme.colors.text,
    marginTop: theme.spacing.md,
  },
  reportError: {
    fontSize: 12,
    color: theme.colors.danger,
    textAlign: "center",
  },
});
