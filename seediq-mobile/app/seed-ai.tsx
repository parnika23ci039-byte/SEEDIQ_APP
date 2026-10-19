import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Row, SliderField, Badge } from "@/components/ui";
import { CropImage } from "@/components/crop-image";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { CROP_VARIETIES } from "@/lib/crops";
import type { ReportData } from "@/lib/report";
import type { SeedViabilityResponse } from "@/lib/types";

export default function SeedAiScreen() {
  const { t } = useI18n();
  const [crop, setCrop] = useState("Wheat");
  // Defaults sit inside the band the seed model actually treats as viable
  // (moisture 10-13.5 %, 100-seed weight >= 45 g) so the first run is coherent
  // with the slider hints.
  const [moisture, setMoisture] = useState(11.5);
  const [weight, setWeight] = useState(52.0);

  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<SeedViabilityResponse | null>(null);

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      const res = await api<SeedViabilityResponse>("/api/seed-viability", {
        method: "POST",
        body: { crop, moisture, weight },
      });
      setData(res);
    } catch (e) {
      setData(null);
      setErrorMsg(
        e instanceof ApiError || e instanceof NetworkError
          ? e.message
          : t("errors.predictionFailed"),
      );
    } finally {
      setIsPredicting(false);
    }
  };

  const viable = data?.result.ensemble === "Viable";

  const shareText = data
    ? [
        t("share.seedTitle"),
        t("share.seedSummary", { crop }),
        t("share.seedMetrics", { moisture, weight }),
        t("share.ensembleVerdictShare", { value: data.result.ensemble }),
        t("share.classicalSvm", { value: data.result.classical }),
        t("share.quantumVqc", { value: data.result.quantum }),
      ].join("\n")
    : null;

  const reportData: ReportData | null = data
    ? {
        title: t("report.seedTitle", { crop }),
        domain: t("report.domainSeed"),
        primaryResult: {
          label: t("report.verdictLabel"),
          value: data.result.ensemble,
          subtext:
            data.result.error ||
            t("report.seedSubtext", { crop, moisture, weight }),
        },
        parameters: [
          { label: t("report.parametersCropVariety"), value: crop },
          { label: t("report.parametersMoistureContent"), value: `${moisture} %`, status: moisture >= 10 && moisture <= 13.5 ? "ok" : "warning" },
          { label: t("report.parametersSeedWeight100"), value: `${weight} g`, status: weight >= 45 ? "ok" : "warning" },
        ],
        models: [
          { model: t("report.modelSvm"), prediction: data.result.classical },
          { model: t("report.modelQuantumVqc"), prediction: data.result.quantum },
          {
            model: t("report.modelEnsemble"),
            prediction: data.result.ensemble,
            note: t(
              data.result.classical === data.result.quantum
                ? "report.modelsAgree"
                : "report.modelsDisagree",
            ),
          },
          ...(data.result.quality_class
            ? [
                {
                  model: t("seedAi.qualityClass"),
                  prediction: data.result.quality_class,
                  note: t("seedAi.qualitySource"),
                },
              ]
            : []),
        ],
        advisories: [
          {
            title: t(
              viable ? "report.advisoryStorageGuidance" : "report.advisoryCorrective",
            ),
            desc: t(viable ? "seedAi.viableMessage" : "seedAi.notViableMessage"),
            priority: t(
              viable ? "report.advisoryPriorityHigh" : "report.advisoryPriorityCritical",
            ),
          },
        ],
      }
    : null;

  return (
    <AiScreenShell
      title={t("seedAi.title")}
      subtitle={t("seedAi.subtitle")}
      isPredicting={isPredicting}
      onPredict={handlePredict}
      onRetry={handlePredict}
      error={errorMsg}
      result={data ? <SeedResult data={data} crop={crop} moisture={moisture} weight={weight} /> : null}
      shareText={shareText}
      reportData={reportData}
      predictLabel={t("seedAi.predict")}
    >
      <View style={styles.pickerShell}>
        <Text style={styles.pickerLabel}>{t("seedAi.cropVariety")}</Text>
        <View style={styles.pickerRowWrap}>
          <PickerInline value={crop} onChange={setCrop} items={CROP_VARIETIES} />
        </View>
      </View>
      <SliderField label={t("seedAi.moistureLabel")} value={moisture} onValueChange={setMoisture} min={5} max={25} step={0.1} unit="%" optimal={[10, 13.5]} hint={t("seedAi.moistureHint")} />
      <SliderField label={t("seedAi.weightLabel")} value={weight} onValueChange={setWeight} min={10} max={100} step={0.5} unit="g" optimal={[45, 70]} hint={t("seedAi.weightHint")} />
    </AiScreenShell>
  );
}

import { Picker } from "@react-native-picker/picker";

function PickerInline({ value, onChange, items }: { value: string; onChange: (v: string) => void; items: string[] }) {
  return (
    <Picker selectedValue={value} onValueChange={(v) => onChange(String(v))} style={{ height: 48 }} dropdownIconColor={theme.colors.textSecondary}>
      {items.map((i) => (
        <Picker.Item key={i} label={i} value={i} />
      ))}
    </Picker>
  );
}

function SeedResult({
  data,
  crop,
  moisture,
  weight,
}: {
  data: SeedViabilityResponse;
  crop: string;
  moisture: number;
  weight: number;
}) {
  const { t } = useI18n();
  const viable = data.result.ensemble === "Viable";
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("seedAi.resultHeading")}</ResultHeading>

      {/* Original SeedIQ crop + storage imagery for the selected crop */}
      <View style={styles.imageRow}>
        <CropImage crop={crop} kind="crop" height={140} label={crop} style={styles.imageHalf} />
        <CropImage crop={crop} kind="storage" height={140} label={t("common.storage")} style={styles.imageHalf} />
      </View>

      <Card style={[styles.resultCard, { borderColor: viable ? theme.colors.primaryBorder : "#EFC7C4" }]}>
        <Text style={styles.resultLabel}>{t("seedAi.ensembleVerdict")}</Text>
        <Text style={[styles.resultValue, { color: viable ? theme.colors.success : theme.colors.danger }]}>
          {data.result.ensemble}
        </Text>
        <Text style={styles.totalText}>
          {crop} · {moisture}% moisture · {weight} g
        </Text>
        <View style={styles.modelRow}>
          <Badge label={`${t("seedAi.classicalBadge")}: ${data.result.classical}`} tone="info" small />
          <Badge label={`Quantum: ${data.result.quantum}`} tone="primary" small />
        </View>
      </Card>

      {/* Viability score + quality grade — the backend's own probability, with
          its provenance stated. The score is the classical model's calibrated
          output, not a lab germination certificate. */}
      {(data.result.viability_score !== undefined || data.result.quality_class) && (
        <Card>
          <Text style={styles.cardTitle}>{t("seedAi.viabilityScore")}</Text>
          {data.result.viability_score !== undefined && data.result.viability_score !== null ? (
            <Text style={[styles.scoreValue, { color: viable ? theme.colors.success : theme.colors.danger }]}>
              {data.result.viability_score.toFixed(1)}%
            </Text>
          ) : null}
          {data.result.quality_class ? (
            <Row
              label={t("seedAi.qualityClass")}
              value={data.result.quality_class}
              tone={data.result.quality_class === "Grade A" ? "success" : data.result.quality_class === "Grade B" ? "warning" : "danger"}
            />
          ) : null}
          <Text style={styles.qualitySource}>
            {data.result.quality_source ?? t("seedAi.qualitySource")}
          </Text>
        </Card>
      )}

      <Card>
        <Text style={styles.cardTitle}>{t("seedAi.whatThisMeans")}</Text>
        <Text style={styles.adviceText}>
          {t(viable ? "seedAi.viableMessage" : "seedAi.notViableMessage")}
        </Text>
        <Row
          label={t("seedAi.modelAgreement")}
          value={t(
            data.result.classical === data.result.quantum
              ? "seedAi.modelsAgree"
              : "seedAi.modelsDisagree",
          )}
          tone={data.result.classical === data.result.quantum ? "success" : "warning"}
        />
        <Row
          label={t("report.modelQuantumVqc")}
          value={data.result.quantum || t("seedAi.quantumUnavailable")}
          tone={data.result.quantum ? "default" : "warning"}
        />
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  imageRow: { flexDirection: "row" as const, gap: theme.spacing.sm },
  imageHalf: { flex: 1, height: 140 },
  resultCard: { alignItems: "center" as const, padding: theme.spacing.xl, borderWidth: 1.5 },
  resultLabel: { fontSize: 12, color: theme.colors.textMuted, textTransform: "uppercase" as const, letterSpacing: 1 },
  resultValue: { fontSize: 32, fontWeight: "800" as const, marginTop: 4 },
  totalText: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 6, textAlign: "center" as const },
  modelRow: { flexDirection: "row" as const, gap: 8, marginTop: theme.spacing.md, flexWrap: "wrap" as const, justifyContent: "center" as const },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
  scoreValue: { fontSize: 30, fontWeight: "800" as const, marginBottom: 6 },
  qualitySource: { fontSize: 11, color: theme.colors.textMuted, lineHeight: 16, marginTop: 6 },
  adviceText: { fontSize: 13, color: theme.colors.textMuted, lineHeight: 19 },
  pickerShell: { gap: 6 },
  pickerLabel: { fontSize: 13, fontWeight: "600", color: theme.colors.text },
  pickerRowWrap: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    overflow: "hidden" as const,
  },
});
