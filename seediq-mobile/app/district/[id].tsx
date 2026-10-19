import React from "react";
import { Text, View, StyleSheet } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { AiScreenShell } from "@/components/ai-screen";
import { Card, Row, Badge, ProgressBar } from "@/components/ui";
import { translate, useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import type { DistrictNotification } from "@/lib/types";

function riskTone(level: string): "danger" | "warning" | "info" | "success" {
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

export default function DistrictDetailScreen() {
  const { t } = useI18n();
  const params = useLocalSearchParams<{ id: string; payload?: string }>();

  let notif: DistrictNotification | null = null;
  try {
    if (params.payload) notif = JSON.parse(params.payload);
  } catch {
    notif = null;
  }

  if (!notif) {
    return (
      <AiScreenShell
        title={t("district.title")}
        subtitle={t("district.unavailableSubtitle")}
        isPredicting={false}
        onPredict={() => {}}
        error={null}
        result={null}
      >
        <Text style={{ color: theme.colors.textMuted, fontSize: 13 }}>
          {t("district.noPayload")}
        </Text>
      </AiScreenShell>
    );
  }

  const tone = riskTone(notif.risk_level);

  return (
    <AiScreenShell
      title={notif.district_name}
      subtitle={`${notif.region} · ${notif.kannada_name}`}
      isPredicting={false}
      onPredict={() => {}}
      error={null}
      result={null}
      shareText={buildShareText(notif)}
      hidePredict
    >
      <Card>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Badge label={notif.risk_level} tone={tone} />
          <Badge label={notif.crop} tone="primary" small />
        </View>
        <Text style={styles.message}>{notif.message}</Text>
        <Text style={styles.action}>
          {t("district.recommendedAction", { action: notif.recommended_action })}
        </Text>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("district.seedStorage")}</Text>
        <Row label={t("district.availableStock")} value={`${notif.stock_tons.toLocaleString()} T`} />
        <Row label={t("district.capacity")} value={`${notif.capacity_tons.toLocaleString()} T`} />
        <Row label={t("district.occupancy")} value={`${notif.occupancy_pct}%`} />
        <ProgressBar value={notif.occupancy_pct} tone={notif.occupancy_pct > 85 ? "warning" : "primary"} />
        <Row label={t("district.currentViability")} value={`${notif.current_viability}%`} tone={notif.current_viability < 60 ? "danger" : notif.current_viability < 75 ? "warning" : "success"} />
        <Row label={t("district.predictedViability")} value={`${notif.predicted_viability}%`} />
        <Row label={t("district.moistureRisk")} value={notif.moisture_risk} />
        <Row
          label={t("district.redistribution")}
          value={t(notif.redistribution_eligible ? "district.eligibleSource" : "district.notEligible")}
          tone={notif.redistribution_eligible ? "success" : "default"}
        />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>
          {t("district.cropStorage", { facility: notif.facility })}
        </Text>
        <Row label={t("district.safeDuration")} value={notif.safe_duration} />
      </Card>
    </AiScreenShell>
  );
}

function buildShareText(n: DistrictNotification): string {
  return [
    translate("share.districtTitle", { district: n.district_name, kannada: n.kannada_name }),
    translate("share.districtRegion", { value: n.region }),
    translate("share.districtRisk", { value: n.risk_level }),
    translate("share.districtCrop", { value: n.crop }),
    translate("share.districtFacility", { value: n.facility }),
    "",
    translate("share.districtStock", {
      stock: n.stock_tons,
      capacity: n.capacity_tons,
      pct: n.occupancy_pct,
    }),
    translate("share.districtViability", {
      current: n.current_viability,
      predicted: n.predicted_viability,
    }),
    translate("share.districtMoisture", { value: n.moisture_risk }),
    translate("share.districtSafeDuration", { value: n.safe_duration }),
    "",
    n.message,
    translate("share.districtAction", { value: n.recommended_action }),
  ].join("\n");
}

const styles = StyleSheet.create({
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
  message: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19, marginTop: 8 },
  action: { fontSize: 13, color: theme.colors.primary, fontWeight: "600", marginTop: 8 },
});
