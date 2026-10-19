import React, { useState } from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { AlertTriangle, ChevronRight, Droplets, Warehouse } from "lucide-react-native";
import { Screen, Card, Badge, Loading, ErrorBanner, EmptyState, ProgressBar, SectionTitle, Stat } from "@/components/ui";
import { useI18n, type TranslationKey } from "@/i18n";
import { useDistrictNotifications, useStorageLive } from "@/lib/hooks";
import { theme } from "@/theme/theme";
import type { DistrictNotification, RiskLevel } from "@/lib/types";

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

const RISK_LABELS: Record<RiskLevel, TranslationKey> = {
  CRITICAL: "alerts.riskCritical",
  WARNING: "alerts.riskWarning",
  MONITOR: "alerts.riskMonitor",
  STABLE: "alerts.riskStable",
};

export default function AlertsScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const notifications = useDistrictNotifications(true);
  const live = useStorageLive(true);

  const [filter, setFilter] = useState<"ALL" | RiskLevel>("ALL");

  const filtered: DistrictNotification[] = (notifications.data?.notifications || []).filter(
    (n) => filter === "ALL" || n.risk_level === filter,
  );

  const s = live.data?.summary;

  return (
    <Screen
      refreshControl={
        <RefreshControl
          refreshing={notifications.isFetching || live.isFetching}
          onRefresh={() => {
            void notifications.refetch();
            void live.refetch();
          }}
          tintColor={theme.colors.primary}
          colors={[theme.colors.primary]}
        />
      }
    >
      <SectionTitle
        action={
          notifications.data ? (
            <Text style={styles.syncText}>{t("alerts.syncsEvery")}</Text>
          ) : undefined
        }
      >
        {t("alerts.title")}
      </SectionTitle>

      {live.isLoading ? (
        <Loading label={t("alerts.loadingTelemetry")} />
      ) : live.isError ? (
        <ErrorBanner
          message={live.error instanceof Error ? live.error.message : t("alerts.errTelemetry")}
          onRetry={() => live.refetch()}
        />
      ) : s ? (
        <View style={{ gap: theme.spacing.md }}>
          <View style={styles.statsRow}>
            <Stat label={t("alerts.critical")} value={s.critical_alerts} />
            <Stat label={t("alerts.warning")} value={s.warning_alerts} />
          </View>
          <View style={styles.statsRow}>
            <Stat label={t("alerts.stable")} value={s.stable_districts} />
            <Stat label={t("alerts.districts")} value={s.total_districts} />
          </View>
          <Card>
            <Text style={styles.cardTitle}>{t("alerts.statewideOccupancy")}</Text>
            <Text style={styles.occupancyValue}>{s.statewide_occupancy_percentage}%</Text>
            <ProgressBar value={s.statewide_occupancy_percentage} tone={s.statewide_occupancy_percentage > 85 ? "warning" : "primary"} />
            <Text style={styles.occupancySub}>
              {t("alerts.occupancySub", {
                stored: s.total_stock_tons.toLocaleString(),
                capacity: s.total_capacity_tons.toLocaleString(),
              })}
            </Text>
          </Card>
        </View>
      ) : null}

      <SectionTitle>{t("alerts.notifications")}</SectionTitle>

      <View style={styles.filterRow}>
        {(["ALL", "CRITICAL", "WARNING", "MONITOR", "STABLE"] as const).map((f) => (
          <Pressable
            key={f}
            onPress={() => setFilter(f)}
            style={[styles.filterChip, filter === f && styles.filterChipActive]}
          >
            <Text style={[styles.filterText, filter === f && styles.filterTextActive]}>
              {f === "ALL" ? t("alerts.filterAll") : t(RISK_LABELS[f])}
            </Text>
          </Pressable>
        ))}
      </View>

      {notifications.isLoading ? (
        <Loading label={t("alerts.loadingNotifications")} />
      ) : notifications.isError ? (
        <ErrorBanner
          message={
            notifications.error instanceof Error
              ? notifications.error.message
              : t("alerts.errNotifications")
          }
          onRetry={() => notifications.refetch()}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle size={40} color={theme.colors.textMuted} />}
          title={t("alerts.emptyTitle")}
          message={t("alerts.emptyMessage")}
        />
      ) : (
        <View style={{ gap: theme.spacing.md }}>
          {filtered.map((n) => (
            <Pressable
              key={n.id}
              onPress={() =>
                router.push({
                  pathname: "/district/[id]",
                  params: { id: n.district_id, payload: JSON.stringify(n) },
                })
              }
            >
              <Card>
                <View style={styles.notifTop}>
                  <Badge label={n.risk_level} tone={riskTone(n.risk_level)} small />
                  <Text style={styles.timeAgo}>{n.time_ago}</Text>
                </View>
                <Text style={styles.notifTitle}>{n.title}</Text>
                <Text style={styles.notifMessage} numberOfLines={3}>
                  {n.message}
                </Text>
                <View style={styles.notifMeta}>
                  <View style={styles.metaItem}>
                    <Warehouse size={13} color={theme.colors.textMuted} />
                    <Text style={styles.metaText}>
                      {t("alerts.occupancyPct", { pct: n.occupancy_pct })}
                    </Text>
                  </View>
                  <View style={styles.metaItem}>
                    <Droplets size={13} color={theme.colors.textMuted} />
                    <Text style={styles.metaText}>
                      {t("alerts.viabilityPct", { pct: n.current_viability })}
                    </Text>
                  </View>
                  <ChevronRight size={16} color={theme.colors.textMuted} />
                </View>
              </Card>
            </Pressable>
          ))}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  syncText: { fontSize: 11, color: theme.colors.textMuted },
  statsRow: { flexDirection: "row", gap: theme.spacing.md },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  occupancyValue: { fontSize: 28, fontWeight: "800", color: theme.colors.text, marginVertical: 6 },
  occupancySub: { fontSize: 12, color: theme.colors.textMuted, marginTop: 6 },
  filterRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: theme.radii.full,
    backgroundColor: theme.colors.surfaceMuted,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  filterChipActive: { backgroundColor: theme.colors.primarySoft, borderColor: theme.colors.primaryBorder },
  filterText: { fontSize: 11, fontWeight: "700", color: theme.colors.textSecondary, letterSpacing: 0.4 },
  filterTextActive: { color: theme.colors.primary },
  notifTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  timeAgo: { fontSize: 11, color: theme.colors.textMuted },
  notifTitle: { fontSize: 14, fontWeight: "700", color: theme.colors.text, marginTop: 6, lineHeight: 19 },
  notifMessage: { fontSize: 12, color: theme.colors.textSecondary, lineHeight: 18, marginTop: 2 },
  notifMeta: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md, marginTop: 8 },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  metaText: { fontSize: 11, color: theme.colors.textMuted },
});
