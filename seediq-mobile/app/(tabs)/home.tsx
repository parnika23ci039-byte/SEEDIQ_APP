import React from "react";
import { Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Sprout,
  TrendingUp,
  Activity,
  CloudSun,
  Droplets,
  Wind,
  ThermometerSun,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
  Bell,
} from "lucide-react-native";
import { Screen, Card, Button, SectionTitle, Stat, Badge, Loading, ErrorBanner } from "@/components/ui";
import { BrandLogo } from "@/components/brand";
import { RecommendationCarousel } from "@/components/recommendations";
import { APP_NAME } from "@/lib/config";
import { useAuth } from "@/lib/auth-context";
import { useI18n, type TranslationKey } from "@/i18n";
import { useDashboard, useLocalWeather, useModelMetrics, weatherCodeKey } from "@/lib/hooks";
import { ApiError, NetworkError } from "@/lib/api";
import { theme } from "@/theme/theme";
import type { ModelMetricEntry, ModelMetricsResponse, PredictionHistoryItem } from "@/lib/types";

// Original SeedIQ landing artwork (already bundled for the About screen).
const PANORAMA = require("../../assets/brand/karnataka_panoramic_landscape.jpg");

const AI_MODULES: {
  href: "/crop-ai" | "/yield-ai" | "/seed-ai" | "/storage-ai" | "/quantum";
  title: TranslationKey;
  desc: TranslationKey;
  icon: typeof Sprout;
}[] = [
  {
    href: "/crop-ai",
    title: "tools.cropTitle",
    desc: "tools.cropDesc",
    icon: Sprout,
  },
  {
    href: "/yield-ai",
    title: "tools.yieldTitle",
    desc: "tools.yieldDesc",
    icon: TrendingUp,
  },
  {
    href: "/seed-ai",
    title: "tools.seedTitle",
    desc: "tools.seedDesc",
    icon: Activity,
  },
  {
    href: "/storage-ai",
    title: "tools.storageTitle",
    desc: "tools.storageDesc",
    icon: ShieldCheck,
  },
  {
    href: "/quantum",
    title: "tools.quantumTitle",
    desc: "tools.quantumDesc",
    icon: CloudSun,
  },
];

function describeHistory(item: PredictionHistoryItem, t: (k: TranslationKey, p?: Record<string, string | number>) => string): string {
  const r = item.results || {};
  if (item.type === "crop") return t("home.historyCrop", { crop: String(r.ensemble ?? "—") });
  if (item.type === "yield") return t("home.historyYield", { value: String(r.ensemble ?? "—") });
  if (item.type === "seed") return t("home.historySeed", { value: String(r.ensemble ?? "—") });
  if (item.type === "storage") return t("home.historyStorage", { value: String((r as any).temp ?? "—") });
  if (item.type === "quantum")
    return t("home.historyQuantum", { value: String(r.prob_success ?? "—") });
  return t("home.historyDefault");
}

/** Artifact file name without path/extension: "yield_prediction/xgb_model.pkl" -> "xgb model". */
function shortModelName(entry: ModelMetricEntry): string {
  const base = (entry.model_name || "").split("/").pop() || "";
  const cleaned = base.replace(/\.pkl$/i, "").replace(/_/g, " ").trim();
  const domain = entry.domain ? `${entry.domain} · ` : "";
  const name = cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : entry.model_name;
  return `${domain}${name}`;
}

/** Headline held-out number for a registry entry, or null when the entry has none. */
function headlineMetric(entry: ModelMetricEntry): { value: string; label: TranslationKey } | null {
  const test = entry.test as Record<string, unknown> | null | undefined;
  if (!test) return null;
  if (typeof test.accuracy === "number") {
    return { value: `${(test.accuracy * 100).toFixed(2)}%`, label: "home.mcTest" };
  }
  if (typeof test.r2 === "number") {
    return { value: `R² ${test.r2.toFixed(4)}`, label: "home.mcTest" };
  }
  return null;
}

/** Cross-validated number from the train split, or null. */
function cvMetric(entry: ModelMetricEntry): string | null {
  const cv = entry.cv as Record<string, unknown> | null | undefined;
  if (!cv) return null;
  if (typeof cv.accuracy_mean === "number") return `${(cv.accuracy_mean * 100).toFixed(2)}%`;
  if (typeof cv.r2_mean === "number") return `R² ${cv.r2_mean.toFixed(4)}`;
  return null;
}

/**
 * Model confidence card. Every number here is read from training_registry.json
 * through /api/model_metrics — nothing is defaulted in the client, so a missing
 * registry renders as "not recorded yet" instead of a placeholder percentage.
 */
function ModelConfidence({
  data,
  loading,
  error,
  onRetry,
}: {
  data?: ModelMetricsResponse;
  loading: boolean;
  error: unknown;
  onRetry: () => void;
}) {
  const { t } = useI18n();

  if (loading) return <Loading label={t("home.modelConfidenceLoading")} />;
  if (error) {
    return (
      <ErrorBanner
        message={
          error instanceof ApiError || error instanceof NetworkError
            ? error.message
            : t("home.modelConfidenceError")
        }
        onRetry={onRetry}
      />
    );
  }
  if (!data?.available || !data.models.length) {
    return (
      <Card>
        <SectionTitle>{t("home.modelPerformance")}</SectionTitle>
        <Text style={styles.confidenceHint}>{data?.note ?? t("home.modelConfidenceMissing")}</Text>
      </Card>
    );
  }

  const status = data.generalization?.status ?? "unknown";
  const statusTone = status === "good" ? "success" : status === "moderate" ? "warning" : "danger";

  return (
    <Card>
      <SectionTitle>{t("home.modelPerformance")}</SectionTitle>
      <Text style={styles.confidenceHint}>{t("home.modelConfidenceHint")}</Text>

      <View style={styles.metricsRow}>
        <Badge label={t("home.mcGeneralization", { status: status.toUpperCase() })} tone={statusTone} small />
        {data.last_run_id ? (
          <Badge
            label={t("home.mcLastRun", {
              id: data.last_run_id,
              date: (data.last_run_at ?? "").slice(0, 10),
            })}
            tone="neutral"
            small
          />
        ) : null}
      </View>

      {data.models.map((m) => {
        const headline = headlineMetric(m);
        const cv = cvMetric(m);
        const gap = m.generalization?.train_test_gap;
        const gapStatus = m.generalization?.status ?? "unknown";
        const gapTone =
          gapStatus === "good" ? "success" : gapStatus === "moderate" ? "warning" : "danger";
        const train = m.train as Record<string, unknown> | null | undefined;
        const trainValue =
          train && typeof train.accuracy === "number"
            ? `${(train.accuracy * 100).toFixed(2)}%`
            : train && typeof train.r2 === "number"
              ? `R² ${train.r2.toFixed(4)}`
              : null;

        return (
          <View key={m.model_name} style={styles.confidenceRow}>
            <View style={styles.confidenceTop}>
              <Text style={styles.confidenceName}>{shortModelName(m)}</Text>
              <Badge
                label={gapStatus === "unknown" ? t("common.notChecked") : `${(Math.abs(gap ?? 0) * 100).toFixed(1)} pp`}
                tone={gapStatus === "unknown" ? "neutral" : gapTone}
                small
              />
            </View>
            <Text style={styles.confidenceMeta} numberOfLines={2}>
              {m.algorithm ?? ""}
            </Text>
            <View style={styles.confidenceValues}>
              <Text style={styles.confidenceValue}>
                {t("home.mcTest")}: {headline ? headline.value : t("home.mcNotSaved")}
              </Text>
              {cv ? <Text style={styles.confidenceValue}>{t("home.mcCv")}: {cv}</Text> : null}
              {trainValue ? <Text style={styles.confidenceValue}>{t("home.mcTrain")}: {trainValue}</Text> : null}
            </View>
            {(m.dataset_provenance === "synthetic-generated" ||
              m.simulated_quantum === true ||
              m.artifact_written === false) && (
              <View style={styles.confidenceTags}>
                {m.dataset_provenance === "synthetic-generated" ? (
                  <Badge label={t("home.mcSynthetic")} tone="warning" small />
                ) : null}
                {m.simulated_quantum === true ? (
                  <Badge label={t("home.mcSimulated")} tone="primary" small />
                ) : null}
                {m.artifact_written === false ? (
                  <Badge label={t("home.mcNotSaved")} tone="danger" small />
                ) : null}
              </View>
            )}
          </View>
        );
      })}
    </Card>
  );
}

export default function HomeScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { user } = useAuth();
  const { weather, loading: weatherLoading, refresh: refreshWeather } = useLocalWeather();
  const dashboard = useDashboard(!!user && !user.isGuest);
  // Model-performance metrics are admin-only. The backend also enforces this
  // (/api/model_metrics returns 401/403 for non-admins), so we never even
  // request the restricted payload for guests or regular users.
  const modelMetrics = useModelMetrics(!!user && user.role === "Admin");

  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return t("home.greetingMorning");
    if (h < 17) return t("home.greetingAfternoon");
    return t("home.greetingEvening");
  })();

  const displayName =
    user?.display_name || user?.name || user?.username || t("common.operator");
  const conditionLabel = t(weatherCodeKey(weather?.current?.weather_code));

  // Real context shown on the recommendation cards — weather readings and the
  // user's own run count. Never a fabricated prediction.
  const recommendationFacts: string[] = [];
  if (weather?.current?.temperature_2m !== undefined) {
    recommendationFacts.push(
      t("home.aiRecWeather", {
        location: weather.locationName ?? t("common.operator"),
        temp: Math.round(weather.current.temperature_2m),
        humidity: weather.current.relative_humidity_2m ?? "--",
      }),
    );
  }
  if (dashboard.data?.total_runs) {
    recommendationFacts.push(t("home.aiRecRuns", { count: dashboard.data.total_runs }));
  }

  return (
    <Screen
      refreshControl={
        <RefreshControl
          refreshing={dashboard.isRefetching || weatherLoading || (user?.role === "Admin" && modelMetrics.isRefetching)}
          onRefresh={() => {
            refreshWeather();
            if (dashboard.isEnabled) void dashboard.refetch();
            if (user?.role === "Admin") void modelMetrics.refetch();
          }}
          tintColor={theme.colors.primary}
          colors={[theme.colors.primary]}
        />
      }
    >
      {/* Greeting */}
      <View style={styles.greetingRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.greeting}>
            {greeting}, <Text style={{ color: theme.colors.primary }}>{displayName}</Text>
          </Text>
          <View style={styles.roleRow}>
            <Badge label={t("home.roleTier", { role: user?.role ?? "Farmer" })} tone="primary" small />
            <Text style={styles.tagline}>{t("app.operatingTagline")}</Text>
          </View>
        </View>
        <Card bordered={false} style={styles.weatherMini}>
          <CloudSun size={22} color={theme.colors.primary} />
          <Text style={styles.weatherTemp}>
            {weather?.current?.temperature_2m !== undefined ? `${Math.round(weather.current.temperature_2m)}°` : "--"}
          </Text>
        </Card>
      </View>

      {/* Brand hero — the client-supplied SeedIQ logo over the original
          Karnataka landscape artwork from the web app. */}
      <View style={styles.hero}>
        <Image source={PANORAMA} style={styles.heroImage} resizeMode="cover" />
        <View style={styles.heroScrim} />
        <View style={styles.heroContent}>
          <BrandLogo width={52} radius={12} />
          <View style={{ flex: 1 }}>
            <Text style={styles.heroTitle}>{APP_NAME}</Text>
            <Text style={styles.heroTagline}>{t("app.tagline")}</Text>
          </View>
        </View>
      </View>

      {/* Auto-rotating AI recommendations (tap any card to open the module) */}
      <SectionTitle>{t("home.aiRecommendations")}</SectionTitle>
      <RecommendationCarousel facts={recommendationFacts} />

      {/* Weather details */}
      <Card>
        <View style={styles.weatherHeader}>
          <Text style={styles.cardTitle}>{t("home.liveWeather")}</Text>
          <Text onPress={refreshWeather} style={styles.linkText}>
            <RefreshCw size={12} color={theme.colors.primary} /> {t("common.refresh")}
          </Text>
        </View>
        <Text style={styles.weatherLocation}>{weather?.locationName ?? t("home.locating")}</Text>
        {weatherLoading && !weather ? (
          <Loading label={t("home.fetchingWeather")} />
        ) : (
          <>
            <Text style={styles.weatherCondition}>{conditionLabel}</Text>
            <View style={styles.weatherGrid}>
              <WeatherCell icon={<ThermometerSun size={16} color={theme.colors.warning} />} label={t("home.feelsLike")} value={`${weather?.current?.apparent_temperature !== undefined ? Math.round(weather.current.apparent_temperature) : "--"}°`} />
              <WeatherCell icon={<Droplets size={16} color={theme.colors.info} />} label={t("home.humidity")} value={`${weather?.current?.relative_humidity_2m ?? "--"}%`} />
              <WeatherCell icon={<Wind size={16} color={theme.colors.primary} />} label={t("home.wind")} value={`${weather?.current?.wind_speed_10m ?? "--"} km/h`} />
              <WeatherCell icon={<Droplets size={16} color={theme.colors.info} />} label={t("home.rainChance")} value={`${weather?.daily?.precipitation_probability_max?.[0] ?? 0}%`} />
            </View>
            <Text style={styles.weatherRange}>
              {t("home.todayRange", {
                min: weather?.daily?.temperature_2m_min?.[0] !== undefined ? Math.round(weather.daily.temperature_2m_min[0]) : "--",
                max: weather?.daily?.temperature_2m_max?.[0] !== undefined ? Math.round(weather.daily.temperature_2m_max[0]) : "--",
              })}
            </Text>
          </>
        )}
      </Card>

      {/* Dashboard stats (real user stats; guests get empty state) */}
      {user && !user.isGuest ? (
        dashboard.isLoading ? (
          <Loading label={t("home.loadingStats")} />
        ) : dashboard.isError ? (
          <ErrorBanner
            message={
              dashboard.error instanceof Error
                ? dashboard.error.message
                : t("home.errStats")
            }
            onRetry={() => dashboard.refetch()}
          />
        ) : dashboard.data ? (
          <>
            <View style={styles.statsRow}>
              <Stat label={t("home.totalRuns")} value={dashboard.data.total_runs} />
              <Stat label={t("home.avgYield")} value={`${dashboard.data.avg_yield} t/ha`} />
            </View>
            <View style={styles.statsRow}>
              <Stat label={t("home.viabilityRate")} value={`${dashboard.data.viability_rate}%`} />
              <Stat label={t("home.topCrop")} value={dashboard.data.top_crop} />
            </View>

            {dashboard.data.history?.length > 0 && (
              <Card>
                <SectionTitle>{t("home.recentActivity")}</SectionTitle>
                {dashboard.data.history.slice(0, 5).map((h, i) => (
                  <View key={i} style={styles.historyRow}>
                    <Badge label={h.type.toUpperCase()} tone="info" small />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.historyText} numberOfLines={1}>
                        {describeHistory(h, t)}
                      </Text>
                      <Text style={styles.historyTime}>{new Date(h.timestamp).toLocaleString()}</Text>
                    </View>
                  </View>
                ))}
              </Card>
            )}
          </>
        ) : null
      ) : (
        <Card>
          <Text style={styles.guestHint}>{t("session.guestHint")}</Text>
        </Card>
      )}

      {/* Model confidence — held-out metrics read from training_registry.json.
          Admin-only: hidden for guests and regular users both in the UI and on
          the backend (/api/model_metrics returns 401/403 for non-admins). */}
      {user?.role === "Admin" && (
        <ModelConfidence
          data={modelMetrics.data}
          loading={modelMetrics.isLoading}
          error={modelMetrics.error}
          onRetry={() => void modelMetrics.refetch()}
        />
      )}

      {/* Quick AI actions */}
      <SectionTitle
        action={
          <Text onPress={() => router.push("/(tabs)/tools")} style={styles.linkText}>
            {t("home.seeAll")}
          </Text>
        }
      >
        {t("home.aiModules")}
      </SectionTitle>
      <View style={styles.moduleGrid}>
        {AI_MODULES.map((m) => {
          const Icon = m.icon;
          return (
            <Pressable
              key={m.href}
              onPress={() => router.push(m.href)}
              style={styles.moduleCard}
            >
            <Card>
              <View style={styles.moduleIconRow}>
                <View style={styles.moduleIconBox}>
                  <Icon size={20} color={theme.colors.primary} />
                </View>
                <ArrowRight size={16} color={theme.colors.textMuted} />
              </View>
              <Text style={styles.moduleTitle}>
                {t(m.title)}
              </Text>
              <Text style={styles.moduleDesc}>{t(m.desc)}</Text>
            </Card>
            </Pressable>
          );
        })}
      </View>

      {/* Alerts teaser */}
      <Button
        label={t("home.viewAlerts")}
        variant="outline"
        icon={<Bell size={16} color={theme.colors.primary} />}
        onPress={() => router.push("/(tabs)/alerts")}
      />
    </Screen>
  );
}

function WeatherCell({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <View style={styles.weatherCell}>
      {icon}
      <Text style={styles.weatherCellLabel}>{label}</Text>
      <Text style={styles.weatherCellValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    height: 118,
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    backgroundColor: theme.colors.navBackground,
    justifyContent: "flex-end",
  },
  heroImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  heroScrim: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(40, 54, 24, 0.45)" },
  heroContent: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
    padding: theme.spacing.md,
  },
  heroTitle: { fontSize: 20, fontWeight: "800", color: theme.palette.mint, letterSpacing: 0.3 },
  heroTagline: { fontSize: 11, fontWeight: "600", color: theme.colors.sage, marginTop: 1 },
  greetingRow: { flexDirection: "row", alignItems: "flex-start", gap: theme.spacing.md },
  greeting: { fontSize: 22, fontWeight: "800", color: theme.colors.text },
  roleRow: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 },
  tagline: { fontSize: 11, color: theme.colors.textMuted },
  weatherMini: { alignItems: "center", padding: theme.spacing.md, gap: 2 },
  weatherTemp: { fontSize: 20, fontWeight: "800", color: theme.colors.text },
  weatherHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cardTitle: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  linkText: { color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  weatherLocation: { fontSize: 13, color: theme.colors.textSecondary },
  weatherCondition: { fontSize: 14, fontWeight: "600", color: theme.colors.text },
  weatherGrid: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.sm },
  weatherCell: {
    flexBasis: "48%",
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    gap: 2,
  },
  weatherCellLabel: { fontSize: 11, color: theme.colors.textMuted },
  weatherCellValue: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  weatherRange: { fontSize: 12, color: theme.colors.textMuted },
  statsRow: { flexDirection: "row", gap: theme.spacing.md },
  historyRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md, paddingVertical: 6 },
  historyText: { fontSize: 13, color: theme.colors.text, fontWeight: "500" },
  historyTime: { fontSize: 11, color: theme.colors.textMuted },
  guestHint: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19 },
  metricsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  confidenceHint: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17, marginBottom: 8 },
  confidenceRow: {
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    gap: 4,
  },
  confidenceTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  confidenceName: { fontSize: 13, fontWeight: "700", color: theme.colors.text, flex: 1, marginRight: 8 },
  confidenceMeta: { fontSize: 11, color: theme.colors.textMuted },
  confidenceValues: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  confidenceValue: { fontSize: 11, color: theme.colors.textSecondary, fontWeight: "600" },
  confidenceTags: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 2 },
  moduleGrid: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.md },
  moduleCard: { flexBasis: "48%", flexGrow: 1 },
  moduleIconRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  moduleIconBox: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: theme.colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  moduleTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginTop: 2 },
  moduleDesc: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17 },
});
