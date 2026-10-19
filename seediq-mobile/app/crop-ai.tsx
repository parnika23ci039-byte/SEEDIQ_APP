import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Row, SliderField, Badge, Loading } from "@/components/ui";
import { CropImage } from "@/components/crop-image";
import { useI18n, type TranslateParams } from "@/i18n";
import { theme } from "@/theme/theme";
import type { ReportData } from "@/lib/report";
import type { CropRecommendationResponse } from "@/lib/types";

export default function CropAiScreen() {
  const { t } = useI18n();
  const [n, setN] = useState(90);
  const [p, setP] = useState(42);
  const [k, setK] = useState(43);
  const [temp, setTemp] = useState(24.5);
  const [hum, setHum] = useState(62);
  const [rain, setRain] = useState(102.5);
  const [ph, setPh] = useState(6.5);

  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<CropRecommendationResponse | null>(null);

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      const res = await api<CropRecommendationResponse>("/api/crop-recommendation", {
        method: "POST",
        body: {
          nitrogen: n,
          phosphorus: p,
          potassium: k,
          temperature: temp,
          humidity: hum,
          rainfall: rain,
          ph,
        },
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

  const soilBullet = (label: string, status: string, advice: string) =>
    t("share.bullet", { label, status, advice });

  const shareText = data
    ? [
        t("share.cropTitle"),
        t("share.recommendedCrop", { value: data.result.ensemble }),
        t("share.classicalModel", { value: data.result.classical }),
        t("share.quantumModel", { value: data.result.quantum }),
        "",
        t("share.soilAnalysis"),
        soilBullet(t("cropAi.nitrogenRow"), data.soil_analysis.nitrogen.status, data.soil_analysis.nitrogen.advice),
        soilBullet(t("cropAi.phosphorusRow"), data.soil_analysis.phosphorus.status, data.soil_analysis.phosphorus.advice),
        soilBullet(t("cropAi.potassiumRow"), data.soil_analysis.potassium.status, data.soil_analysis.potassium.advice),
        soilBullet(t("cropAi.phRow"), data.soil_analysis.ph.status, data.soil_analysis.ph.advice),
      ].join("\n")
    : null;

  const reportData: ReportData | null = data
    ? {
        title: t("report.cropTitle"),
        domain: t("report.domainCrop"),
        primaryResult: {
          label: t("report.optimalCropLabel"),
          value: data.result.ensemble,
          subtext: data.result.error || t("report.ensembleSubtext"),
        },
        parameters: [
          { label: t("report.parametersNitrogen"), value: `${n} mg/kg`, status: soilStatusToReport(data.soil_analysis.nitrogen.status) },
          { label: t("report.parametersPhosphorus"), value: `${p} mg/kg`, status: soilStatusToReport(data.soil_analysis.phosphorus.status) },
          { label: t("report.parametersPotassium"), value: `${k} mg/kg`, status: soilStatusToReport(data.soil_analysis.potassium.status) },
          { label: t("report.parametersPh"), value: `${ph}` },
          { label: t("report.parametersTemperature"), value: `${temp} °C` },
          { label: t("report.parametersHumidity"), value: `${hum} %` },
          { label: t("report.parametersRainfall"), value: `${rain} mm` },
        ],
        models: [
          { model: t("report.modelRf"), prediction: data.result.classical },
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
        ],
        advisories: [
          { title: t("report.advisoryNitrogen", { status: data.soil_analysis.nitrogen.status }), desc: data.soil_analysis.nitrogen.advice },
          { title: t("report.advisoryPhosphorus", { status: data.soil_analysis.phosphorus.status }), desc: data.soil_analysis.phosphorus.advice },
          { title: t("report.advisoryPotassium", { status: data.soil_analysis.potassium.status }), desc: data.soil_analysis.potassium.advice },
          { title: t("report.advisoryPh", { status: data.soil_analysis.ph.status }), desc: data.soil_analysis.ph.advice },
          ...(data.growth_plan || []).map((s) => ({
            title: t("report.advisoryGrowthStep", { week: s.week, stage: s.stage }),
            desc: s.action,
          })),
          ...(data.disease_advisory || []).map((d: any) => ({
            title: String(d?.name || d?.disease || t("report.advisoryDiseaseFallback")),
            desc: [
              d?.symptoms && t("report.advisorySymptoms", { value: d.symptoms }),
              d?.treatment && t("report.advisoryTreatment", { value: d.treatment }),
              d?.prevention && t("report.advisoryPrevention", { value: d.prevention }),
            ]
              .filter(Boolean)
              .join(" · "),
          })),
        ],
      }
    : null;

  return (
    <AiScreenShell
      title={t("cropAi.title")}
      subtitle={t("cropAi.subtitle")}
      isPredicting={isPredicting}
      onPredict={handlePredict}
      onRetry={handlePredict}
      error={errorMsg}
      result={data ? <CropResult data={data} /> : null}
      shareText={shareText}
      reportData={reportData}
      predictLabel={t("cropAi.predict")}
    >
      <Text style={styles.sectionLabel}>{t("cropAi.soilNutrients")}</Text>
      <SliderField label={t("cropAi.nLabel")} value={n} onValueChange={setN} min={0} max={140} unit="mg/kg" optimal={[60, 100]} hint={t("cropAi.nHint")} />
      <SliderField label={t("cropAi.pLabel")} value={p} onValueChange={setP} min={0} max={140} unit="mg/kg" optimal={[30, 60]} hint={t("cropAi.pHint")} />
      <SliderField label={t("cropAi.kLabel")} value={k} onValueChange={setK} min={0} max={200} unit="mg/kg" optimal={[40, 80]} hint={t("cropAi.kHint")} />

      <Text style={styles.sectionLabel}>{t("cropAi.climateSection")}</Text>
      <SliderField label={t("cropAi.temperatureLabel")} value={temp} onValueChange={setTemp} min={0} max={50} step={0.1} unit="°C" optimal={[18, 30]} />
      <SliderField label={t("cropAi.humidityLabel")} value={hum} onValueChange={setHum} min={0} max={100} step={0.1} unit="%" optimal={[40, 70]} />
      <SliderField label={t("cropAi.rainfallLabel")} value={rain} onValueChange={setRain} min={0} max={300} step={0.5} unit="mm" optimal={[80, 200]} />
      <SliderField label={t("cropAi.phLabel")} value={ph} onValueChange={setPh} min={0} max={14} step={0.1} unit="pH" optimal={[6.0, 7.5]} />
    </AiScreenShell>
  );
}

function CropResult({ data }: { data: CropRecommendationResponse }) {
  const { t } = useI18n();
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("cropAi.resultHeading")}</ResultHeading>

      {/* Original SeedIQ crop photo for the recommended crop */}
      <CropImage crop={data.result.ensemble} kind="crop" height={180} label={data.result.ensemble} />

      <Card style={styles.resultCard}>
        <Text style={styles.resultLabel}>{t("cropAi.ensembleConsensus")}</Text>
        <Text style={styles.resultValue}>{data.result.ensemble}</Text>
        <View style={styles.modelRow}>
          <Badge label={t("cropAi.classicalBadge", { value: data.result.classical })} tone="info" small />
          <Badge label={t("cropAi.quantumBadge", { value: data.result.quantum })} tone="primary" small />
        </View>
        {data.result.error ? (
          <Text style={styles.modelError}>{t("cropAi.modelNote", { note: data.result.error })}</Text>
        ) : null}
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("cropAi.soilHealth")}</Text>
        <Row label={t("cropAi.nitrogenRow")} value={data.soil_analysis.nitrogen.status} tone={statusTone(data.soil_analysis.nitrogen.status)} />
        <Text style={styles.adviceText}>{data.soil_analysis.nitrogen.advice}</Text>
        <Row label={t("cropAi.phosphorusRow")} value={data.soil_analysis.phosphorus.status} tone={statusTone(data.soil_analysis.phosphorus.status)} />
        <Text style={styles.adviceText}>{data.soil_analysis.phosphorus.advice}</Text>
        <Row label={t("cropAi.potassiumRow")} value={data.soil_analysis.potassium.status} tone={statusTone(data.soil_analysis.potassium.status)} />
        <Text style={styles.adviceText}>{data.soil_analysis.potassium.advice}</Text>
        <Row label={t("cropAi.phRow")} value={data.soil_analysis.ph.status} tone={statusTone(data.soil_analysis.ph.status)} />
        <Text style={styles.adviceText}>{data.soil_analysis.ph.advice}</Text>
      </Card>

      {data.growth_plan?.length > 0 && (
        <Card>
          <Text style={styles.cardTitle}>
            {t("cropAi.growthPlan", { crop: data.result.ensemble })}
          </Text>
          {data.growth_plan.map((step, i) => (
            <View key={i} style={styles.growthStep}>
              <Badge label={step.week} tone="primary" small />
              <Text style={styles.growthStage}>{step.stage}</Text>
              <Text style={styles.adviceText}>{step.action}</Text>
            </View>
          ))}
        </Card>
      )}

      {data.disease_advisory?.length > 0 && (
        <Card>
          <Text style={styles.cardTitle}>{t("cropAi.diseaseAdvisory")}</Text>
          {data.disease_advisory.map((d: any, i: number) => (
            <View key={i} style={styles.growthStep}>
              <Text style={styles.growthStage}>
                {d?.name || d?.disease || t("cropAi.advisoryFallback")}
              </Text>
              {d?.symptoms ? (
                <Text style={styles.adviceText}>
                  {t("cropAi.symptoms", { value: d.symptoms })}
                </Text>
              ) : null}
              {d?.treatment ? (
                <Text style={styles.adviceText}>
                  {t("cropAi.treatment", { value: d.treatment })}
                </Text>
              ) : null}
              {d?.prevention ? (
                <Text style={styles.adviceText}>
                  {t("cropAi.prevention", { value: d.prevention })}
                </Text>
              ) : null}
            </View>
          ))}
        </Card>
      )}
    </View>
  );
}

function statusTone(status: string): "success" | "warning" | "danger" | "info" {
  const s = status.toLowerCase();
  if (s.includes("high") || s.includes("optimal") || s.includes("neutral") || s.includes("medium")) return "success";
  if (s.includes("low") || s.includes("acidic") || s.includes("deficient")) return "warning";
  if (s.includes("alkaline")) return "info";
  return "info";
}

function soilStatusToReport(status: string): "ok" | "warning" | undefined {
  return statusTone(status) === "warning" ? "warning" : "ok";
}

const styles = StyleSheet.create({
  sectionLabel: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: theme.spacing.xs,
  },
  resultCard: { alignItems: "center" as const, padding: theme.spacing.xl },
  resultLabel: { fontSize: 12, color: theme.colors.textMuted, textTransform: "uppercase" as const, letterSpacing: 1 },
  resultValue: { fontSize: 32, fontWeight: "800" as const, color: theme.colors.primary, marginTop: 4 },
  modelRow: { flexDirection: "row" as const, gap: 8, marginTop: theme.spacing.md, flexWrap: "wrap" as const, justifyContent: "center" as const },
  modelError: { fontSize: 11, color: theme.colors.warning, marginTop: 8, textAlign: "center" as const },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
  adviceText: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17, marginBottom: 6 },
  growthStep: { gap: 2, marginBottom: theme.spacing.md },
  growthStage: { fontSize: 14, fontWeight: "600", color: theme.colors.text },
});
