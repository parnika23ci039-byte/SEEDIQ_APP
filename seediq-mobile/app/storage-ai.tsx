import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Row, Badge, ProgressBar, PickerField } from "@/components/ui";
import { CropImage } from "@/components/crop-image";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { CROP_VARIETIES } from "@/lib/crops";
import type { ReportData } from "@/lib/report";
import type { StorageRecommendationResponse } from "@/lib/types";

export default function StorageAiScreen() {
  const { t } = useI18n();
  const [crop, setCrop] = useState("Rice");
  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<StorageRecommendationResponse | null>(null);

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      const res = await api<StorageRecommendationResponse>("/api/storage-recommendation", {
        method: "POST",
        body: { crop },
      });
      setData(res);
    } catch (e) {
      setData(null);
      setErrorMsg(
        e instanceof ApiError || e instanceof NetworkError
          ? e.message
          : t("errors.recommendationFailed"),
      );
    } finally {
      setIsPredicting(false);
    }
  };

  const shareText = data
    ? [
        t("share.storageTitle"),
        `${t("yieldAi.cropLabel")}: ${data.crop}`,
        t("share.storageOptimalTemp", { value: data.result.temp }),
        t("share.storageOptimalHumidity", { value: data.result.hum }),
        t("share.storageProtocolShare", { value: data.result.pres }),
        t("share.storageShelfLife", { value: data.result.shelf_life }),
        t("share.storageFungus", { value: data.result.fungus }),
        t("share.storageInsects", { value: data.result.insects }),
        t("share.storageRiskScore", { value: data.result.risk_score }),
      ].join("\n")
    : null;

  const reportData: ReportData | null = data
    ? {
        title: t("report.storageTitle", { crop: data.crop }),
        domain: t("report.domainStorage"),
        primaryResult: {
          label: t("report.shelfLifeLabel"),
          value: data.result.shelf_life,
          subtext: t("report.shelfLifeSubtext", { score: data.result.risk_score }),
        },
        parameters: [
          { label: t("report.parametersCrop"), value: data.crop },
          { label: t("report.parametersOptimalTemp"), value: data.result.temp },
          { label: t("report.parametersOptimalHumidity"), value: data.result.hum },
          { label: t("report.parametersShelfLife"), value: data.result.shelf_life },
          {
            label: t("report.parametersRiskScore"),
            value: `${data.result.risk_score}/100`,
            status: data.result.risk_score >= 60 ? "danger" : data.result.risk_score >= 35 ? "warning" : "ok",
          },
        ],
        advisories: [
          {
            title: t("report.advisoryPreservation"),
            desc: data.result.pres,
            priority: t("report.advisoryPriorityHigh"),
          },
          { title: t("report.advisoryFungus"), desc: data.result.fungus },
          { title: t("report.advisoryInsects"), desc: data.result.insects },
        ],
        summaryNotes: t("report.storageSummaryNotes"),
      }
    : null;

  return (
    <AiScreenShell
      title={t("storageAi.title")}
      subtitle={t("storageAi.subtitle")}
      isPredicting={isPredicting}
      onPredict={handlePredict}
      onRetry={handlePredict}
      error={errorMsg}
      result={data ? <StorageResult data={data} /> : null}
      shareText={shareText}
      reportData={reportData}
      predictLabel={t("storageAi.predict")}
    >
      {/* Original SeedIQ crop + storage imagery for the selected crop */}
      <View style={styles.imageRow}>
        <CropImage crop={crop} kind="crop" height={150} label={crop} style={styles.imageHalf} />
        <CropImage crop={crop} kind="storage" height={150} label={t("common.storage")} style={styles.imageHalf} />
      </View>
      <PickerField label={t("storageAi.cropLabel")} value={crop} onValueChange={setCrop} items={CROP_VARIETIES} />
    </AiScreenShell>
  );
}

function StorageResult({ data }: { data: StorageRecommendationResponse }) {
  const { t } = useI18n();
  const risk = data.result.risk_score;
  const riskTone = risk >= 60 ? "danger" : risk >= 35 ? "warning" : "success";
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("storageAi.resultHeading", { crop: data.crop })}</ResultHeading>

      <Card>
        <View style={styles.titleRow}>
          <Text style={styles.cardTitle}>{t("storageAi.optimalConditions")}</Text>
          <Badge
            label={
              data.result.crop_specific === false
                ? t("storageAi.genericDefaultBadge")
                : t("storageAi.staticBadge")
            }
            tone={data.result.crop_specific === false ? "warning" : "info"}
            small
          />
          <Badge label={t("storageAi.notLiveBadge")} tone="neutral" small />
        </View>
        <Row label={t("storageAi.temperatureRow")} value={data.result.temp} />
        <Row label={t("storageAi.humidityRow")} value={data.result.hum} />
        <Row label={t("storageAi.shelfLifeRow")} value={data.result.shelf_life} />
        <Row label={t("storageAi.riskScoreRow")} value={`${risk}/100`} tone={riskTone} />
        <View style={{ marginTop: 8 }}>
          <ProgressBar value={risk} tone={riskTone} />
        </View>
        <Row
          label={t("storageAi.dataSourceLabel")}
          value={data.result.source ?? t("common.unavailable")}
        />
        <Text style={styles.dataSourceNote}>
          {data.result.protocol_note ?? data.result.note ?? t("storageAi.protocolNote")}
        </Text>
        {data.result.crop_specific === false ? (
          <Text style={styles.genericNotice}>
            {t("storageAi.genericDefaultNotice", { crop: data.crop })}
          </Text>
        ) : null}
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("storageAi.protectionGuidance")}</Text>
        <Text style={styles.blockLabel}>{t("storageAi.preservationProtocol")}</Text>
        <Text style={styles.adviceText}>{data.result.pres}</Text>
        <Text style={styles.blockLabel}>{t("storageAi.fungusRisk")}</Text>
        <Text style={styles.adviceText}>{data.result.fungus}</Text>
        <Text style={styles.blockLabel}>{t("storageAi.insectControl")}</Text>
        <Text style={styles.adviceText}>{data.result.insects}</Text>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  imageRow: { flexDirection: "row" as const, gap: theme.spacing.sm },
  imageHalf: { flex: 1, height: 150 },
  titleRow: {
    flexDirection: "row" as const,
    alignItems: "center",
    flexWrap: "wrap" as const,
    gap: 6,
    marginBottom: 6,
  },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },
  genericNotice: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17, marginTop: 6 },
  blockLabel: { fontSize: 12, fontWeight: "700", color: theme.colors.textSecondary, textTransform: "uppercase" as const, letterSpacing: 0.5, marginTop: 8 },
  adviceText: { fontSize: 13, color: theme.colors.textMuted, lineHeight: 19 },
  dataSourceNote: { fontSize: 11, color: theme.colors.textMuted, lineHeight: 16, marginTop: 8, fontStyle: "italic" as const },
});
