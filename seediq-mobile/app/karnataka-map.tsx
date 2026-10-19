import React, { useMemo, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, ChevronRight, MapPin, RefreshCw } from "lucide-react-native";
import { Badge, Card, ErrorBanner, Loading, ProgressBar, Row, SectionTitle, Stat } from "@/components/ui";
import { KarnatakaMap, mapLegend, type DistrictRisk, type RiskLevel } from "@/components/karnataka-map";
import { useI18n, type TranslationKey } from "@/i18n";
import { useStorageLive } from "@/lib/hooks";
import { normalizeDistrictName } from "@/lib/karnataka-geo";
import { STATUS_BAR_TOP } from "@/lib/layout";
import { theme } from "@/theme/theme";
import { getActiveLanguage } from "@/i18n";

const RISK_LABELS: Record<RiskLevel, TranslationKey> = {
  CRITICAL: "alerts.riskCritical",
  WARNING: "alerts.riskWarning",
  MONITOR: "alerts.riskMonitor",
  STABLE: "alerts.riskStable",
};

function riskTone(level: RiskLevel): "danger" | "warning" | "info" | "success" {
  switch (level) {
    case "CRITICAL":
      return "danger";
    case "WARNING":
      return "warning";
    case "MONITOR":
      return "info";
    default:
      return "success";
  }
}

/**
 * Karnataka district map.
 *
 * Boundaries are the real district polygons; every colour and number comes from
 * `/api/districts/storage-live`. Districts the backend has no telemetry for are
 * drawn neutral rather than guessed at.
 */
export default function KarnatakaMapScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const live = useStorageLive(true);

  const [selected, setSelected] = useState<string | null>(null);
  const [showLabels, setShowLabels] = useState(true);
  const [showRisk, setShowRisk] = useState(true);

  const language = getActiveLanguage();

  const risks = useMemo(() => {
    const out: Record<string, DistrictRisk> = {};
    for (const d of live.data?.districts ?? []) {
      out[normalizeDistrictName(d.district_name)] = {
        risk: (d.seed_storage?.risk_level ?? "STABLE") as RiskLevel,
        badge: `${Math.round(d.seed_storage?.occupancy_percentage ?? 0)}%`,
      };
    }
    return out;
  }, [live.data]);

  const district = useMemo(
    () =>
      live.data?.districts.find(
        (d) => normalizeDistrictName(d.district_name) === normalizeDistrictName(selected ?? ""),
      ) ?? null,
    [live.data, selected],
  );

  const summary = live.data?.summary;
  const lastUpdated = live.data?.last_updated
    ? new Date(live.data.last_updated).toLocaleTimeString()
    : "—";

  return (
    <View style={styles.fill}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <ArrowLeft size={20} color={theme.colors.textInverse} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.topTitle}>{t("map.title")}</Text>
          <Text style={styles.topSubtitle}>{t("map.subtitle")}</Text>
        </View>
        <MapPin size={20} color={theme.colors.sage} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={live.isFetching}
            onRefresh={() => void live.refetch()}
            tintColor={theme.colors.primary}
            colors={[theme.colors.primary]}
          />
        }
      >
        {live.isLoading ? <Loading label={t("map.loading")} /> : null}

        {live.isError ? (
          <ErrorBanner
            message={live.error instanceof Error ? live.error.message : t("errors.network")}
            onRetry={() => live.refetch()}
          />
        ) : null}

        <KarnatakaMap
          risks={risks}
          selected={selected}
          onSelectDistrict={setSelected}
          showLabels={showLabels}
          showRisk={showRisk}
          height={430}
        />

        <Text style={styles.hint}>{t("map.tapHint")}</Text>

        {/* ------------------------------------------------------- layers */}
        <Card>
          <Text style={styles.cardTitle}>{t("map.layers")}</Text>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>{t("map.showRisk")}</Text>
            <Switch
              value={showRisk}
              onValueChange={setShowRisk}
              trackColor={{ false: theme.colors.surfaceMuted, true: theme.colors.primary }}
              thumbColor={theme.colors.surface}
            />
          </View>
          <View style={styles.toggleRow}>
            <Text style={styles.toggleLabel}>{t("map.showLabels")}</Text>
            <Switch
              value={showLabels}
              onValueChange={setShowLabels}
              trackColor={{ false: theme.colors.surfaceMuted, true: theme.colors.primary }}
              thumbColor={theme.colors.surface}
            />
          </View>

          <Text style={styles.legendTitle}>{t("map.legend")}</Text>
          <View style={styles.legendWrap}>
            {mapLegend().map((l) => (
              <View key={l.level} style={styles.legendItem}>
                <View style={[styles.swatch, { backgroundColor: l.color }]} />
                <Text style={styles.legendLabel}>{t(RISK_LABELS[l.level])}</Text>
              </View>
            ))}
            <View style={styles.legendItem}>
              <View style={[styles.swatch, { backgroundColor: theme.colors.surfaceMuted }]} />
              <Text style={styles.legendLabel}>{t("map.noData")}</Text>
            </View>
          </View>
        </Card>

        {/* --------------------------------------------------- statewide */}
        {summary ? (
          <>
            <SectionTitle
              action={
                <Text onPress={() => void live.refetch()} style={styles.linkText}>
                  <RefreshCw size={12} color={theme.colors.primary} /> {t("common.refresh")}
                </Text>
              }
            >
              {t("alerts.title")}
            </SectionTitle>
            <View style={styles.statsRow}>
              <Stat label={t("alerts.critical")} value={summary.critical_alerts} />
              <Stat label={t("alerts.warning")} value={summary.warning_alerts} />
            </View>
            <View style={styles.statsRow}>
              <Stat label={t("map.capacity")} value={`${summary.statewide_occupancy_percentage}%`} />
              <Stat label={t("map.district")} value={summary.total_districts} />
            </View>
            <Text style={styles.syncNote}>
              {t("map.lastSync")}: {lastUpdated}
            </Text>
          </>
        ) : null}

        {/* --------------------------------------------------- selected */}
        <SectionTitle>{t("map.selected")}</SectionTitle>
        {district ? (
          <Card>
            <View style={styles.districtHead}>
              <View style={{ flex: 1 }}>
                <Text style={styles.districtName}>
                  {language === "kn" && district.kannada_name
                    ? district.kannada_name
                    : district.district_name}
                </Text>
                <Text style={styles.districtMeta}>
                  {district.region} · {district.primary_crop}
                </Text>
              </View>
              <Badge
                label={t(RISK_LABELS[(district.seed_storage?.risk_level ?? "STABLE") as RiskLevel])}
                tone={riskTone((district.seed_storage?.risk_level ?? "STABLE") as RiskLevel)}
              />
            </View>

            <Row
              label={t("map.storedGrain")}
              value={`${district.seed_storage?.available_stock_tons ?? 0} t`}
            />
            <Row
              label={t("map.capacity")}
              value={`${district.seed_storage?.occupancy_percentage ?? 0}%`}
            />
            <View style={{ marginTop: 6 }}>
              <ProgressBar
                value={district.seed_storage?.occupancy_percentage ?? 0}
                tone={riskTone((district.seed_storage?.risk_level ?? "STABLE") as RiskLevel)}
              />
            </View>
            <Row label={t("map.temperature")} value={district.crop_storage?.optimal_temp ?? "—"} />
            <Row label={t("map.humidity")} value={district.crop_storage?.optimal_humidity ?? "—"} />
            <Row
              label={t("home.viabilityRate")}
              value={`${district.seed_storage?.current_viability_percentage ?? 0}%`}
            />
            <Row
              label={t("map.riskLevel")}
              value={String(district.crop_storage?.risk_score ?? 0)}
              tone={riskTone((district.seed_storage?.risk_level ?? "STABLE") as RiskLevel)}
            />

            <Pressable onPress={() => router.push("/(tabs)/alerts")} style={styles.alertsLink}>
              <Text style={styles.linkText}>{t("map.openAlerts")}</Text>
              <ChevronRight size={14} color={theme.colors.primary} />
            </Pressable>
          </Card>
        ) : (
          <Card>
            <Text style={styles.hintMuted}>{t("map.tapHint")}</Text>
          </Card>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: theme.colors.background },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    // Clears the system status bar: this row's Back control is otherwise drawn
    // under it and the system consumes every tap.
    paddingTop: STATUS_BAR_TOP + theme.spacing.xs,
    paddingBottom: theme.spacing.md,
    backgroundColor: theme.colors.navBackground,
  },
  backBtn: { padding: 4 },
  topTitle: { fontSize: 18, fontWeight: "800", color: theme.colors.textInverse },
  topSubtitle: { fontSize: 11, color: theme.colors.sage, marginTop: 1 },
  content: { padding: theme.spacing.lg, gap: theme.spacing.md, paddingBottom: 60 },

  hint: { fontSize: 11.5, color: theme.colors.textMuted, lineHeight: 16 },
  hintMuted: { fontSize: 13, color: theme.colors.textMuted, lineHeight: 18 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  toggleLabel: { fontSize: 13, color: theme.colors.textSecondary },
  legendTitle: {
    fontSize: 11,
    fontWeight: "700",
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: theme.spacing.md,
  },
  legendWrap: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.md, marginTop: 6 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  swatch: { width: 14, height: 14, borderRadius: 4, borderWidth: 1, borderColor: theme.colors.border },
  legendLabel: { fontSize: 11.5, color: theme.colors.textSecondary },

  statsRow: { flexDirection: "row", gap: theme.spacing.md },
  syncNote: { fontSize: 11, color: theme.colors.textMuted },

  districtHead: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  districtName: { fontSize: 17, fontWeight: "800", color: theme.colors.text },
  districtMeta: { fontSize: 12, color: theme.colors.textMuted, marginTop: 1 },
  alertsLink: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: theme.spacing.sm },
  linkText: { color: theme.colors.primary, fontWeight: "700", fontSize: 13 },
});
