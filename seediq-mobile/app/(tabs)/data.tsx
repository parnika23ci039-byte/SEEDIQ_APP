import React from "react";
import { Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { FileSpreadsheet, UploadCloud, CheckCircle2, Activity, Lock } from "lucide-react-native";
import { Screen, Card, Badge, Loading, ErrorBanner, EmptyState, Button, SectionTitle } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { useDatasets } from "@/lib/hooks";
import { theme } from "@/theme/theme";
import type { DatasetEntry } from "@/lib/types";

export default function DataScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { user } = useAuth();
  const datasets = useDatasets(!!user);

  const canUpload = user?.role === "Admin" || user?.role === "Researcher";

  const statusTone = (status: string | null | undefined): "success" | "info" | "neutral" => {
    const s = (status || "").toLowerCase();
    if (s.includes("ready") || s.includes("active")) return "success";
    if (s.includes("training")) return "info";
    return "neutral";
  };

  return (
    <Screen
      refreshControl={
        <RefreshControl
          refreshing={datasets.isFetching}
          onRefresh={() => datasets.refetch()}
          tintColor={theme.colors.primary}
          colors={[theme.colors.primary]}
        />
      }
    >
      <SectionTitle
        action={
          <Text style={styles.countText}>
            {datasets.data ? t("data.datasetsCount", { count: datasets.data.length }) : ""}
          </Text>
        }
      >
        {t("data.vault")}
      </SectionTitle>

      {canUpload ? (
        <Button
          label={t("data.uploadCsv")}
          icon={<UploadCloud size={16} color="#fff" />}
          onPress={() => router.push("/upload")}
        />
      ) : (
        <Card>
          <View style={styles.lockRow}>
            <Lock size={16} color={theme.colors.warning} />
            <Text style={styles.lockText}>
              {t("data.uploadLocked", { role: user?.role ?? "" })}
            </Text>
          </View>
        </Card>
      )}

      {datasets.isLoading ? (
        <Loading label={t("data.loading")} />
      ) : datasets.isError ? (
        <ErrorBanner
          message={
            datasets.error instanceof Error ? datasets.error.message : t("data.errLoad")
          }
          onRetry={() => datasets.refetch()}
        />
      ) : !datasets.data || datasets.data.length === 0 ? (
        <EmptyState
          icon={<FileSpreadsheet size={40} color={theme.colors.textMuted} />}
          title={t("data.emptyTitle")}
          message={t("data.emptyMessage")}
        />
      ) : (
        <View style={{ gap: theme.spacing.md }}>
          {datasets.data.map((ds: DatasetEntry) => (
            <Card key={ds.id}>
              <View style={styles.dsTop}>
                <View style={styles.dsIconBox}>
                  <FileSpreadsheet size={18} color={theme.colors.primary} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.dsName} numberOfLines={1}>
                    {ds.name}
                  </Text>
                  <Text style={styles.dsId}>
                    {ds.id} · {ds.type}
                  </Text>
                </View>
                <Badge
                  label={ds.status}
                  tone={statusTone(ds.status)}
                  small
                />
              </View>
              <View style={styles.dsMeta}>
                <Text style={styles.dsMetaText}>{t("data.rows", { count: ds.rows })}</Text>
                <Text style={styles.dsMetaText}>{ds.size}</Text>
                <Text style={styles.dsMetaText}>{ds.date}</Text>
              </View>
            </Card>
          ))}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  countText: { fontSize: 12, color: theme.colors.textMuted },
  lockRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  lockText: { flex: 1, fontSize: 13, color: theme.colors.warning, lineHeight: 18 },
  dsTop: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  dsIconBox: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: theme.colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  dsName: { fontSize: 14, fontWeight: "600", color: theme.colors.text },
  dsId: { fontSize: 11, color: theme.colors.textMuted, marginTop: 1 },
  dsMeta: { flexDirection: "row", gap: theme.spacing.lg, marginTop: theme.spacing.sm, flexWrap: "wrap" },
  dsMetaText: { fontSize: 12, color: theme.colors.textSecondary },
});
