import React, { useCallback, useMemo, useState } from "react";
import { Pressable, Text, View, StyleSheet } from "react-native";
import { useRouter } from "expo-router";
import { ArrowRight, Atom } from "lucide-react-native";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Row, SliderField, PickerField, Badge, ProgressBar } from "@/components/ui";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { encodeFeatures, simulate, vqcOutcome } from "@/lib/quantum";
import type { ReportData } from "@/lib/report";
import type {
  CropRecommendationResponse,
  QuantumMLResponse,
  SeedViabilityResponse,
  YieldPredictionResponse,
} from "@/lib/types";

const CROPS = ["Rice", "Wheat", "Maize", "Sugarcane", "Cotton"];
const SEASONS = ["Kharif", "Rabi", "Zaid", "Summer", "Winter", "Autumn", "Spring", "Whole Year"];

/**
 * Results assembled from the per-module endpoints plus the on-device VQC when
 * the aggregate `/api/quantum-ml` stack cannot load its models.
 */
interface FallbackData {
  cropClassical: string;
  cropQuantum: string;
  yieldClassical: number;
  yieldQuantum: number | null;
  seedClassical: string;
  seedQuantum: string;
  vqcProbability: number;
  vqcFavourable: boolean;
  backendNote: string;
}

export default function QuantumScreen() {
  const { t } = useI18n();
  const router = useRouter();
  // Crop inputs
  const [n, setN] = useState(90);
  const [p, setP] = useState(42);
  const [k, setK] = useState(43);
  const [temp, setTemp] = useState(24.5);
  const [hum, setHum] = useState(62);
  const [ph, setPh] = useState(6.5);
  const [rain, setRain] = useState(102.5);
  // Yield inputs
  const [crop, setCrop] = useState("Rice");
  const [season, setSeason] = useState("Kharif");
  const [area, setArea] = useState(5);
  // Seed inputs
  // Same viable seed band as the Seed AI screen, so the aggregate run starts
  // from a combination the seed model can accept.
  const [moisture, setMoisture] = useState(11.5);
  const [weight, setWeight] = useState(52.0);

  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<QuantumMLResponse | null>(null);
  const [fallback, setFallback] = useState<FallbackData | null>(null);

  // The on-device VQC for the current agronomic inputs. Cheap enough to keep
  // reactive so the Quantum Labs numbers always match what is on screen.
  const vqc = useMemo(
    () => simulate(encodeFeatures({ nitrogen: n, phosphorus: p, potassium: k, temperature: temp, humidity: hum, ph, rainfall: rain, moisture, weight })),
    [n, p, k, temp, hum, ph, rain, moisture, weight],
  );

  const loadFallback = useCallback(
    async (backendNote: string): Promise<void> => {
      const [cropRes, yieldRes, seedRes] = await Promise.all([
        api<CropRecommendationResponse>("/api/crop-recommendation", {
          method: "POST",
          body: { nitrogen: n, phosphorus: p, potassium: k, temperature: temp, humidity: hum, ph, rainfall: rain },
        }),
        // Contract: { crop, area_hectares } — season is not a model input any
        // more and is deliberately not sent (it stays a report label).
        api<YieldPredictionResponse>("/api/yield-prediction", {
          method: "POST",
          body: { crop, area_hectares: area },
        }),
        api<SeedViabilityResponse>("/api/seed-viability", {
          method: "POST",
          body: { crop, moisture, weight },
        }),
      ]);
      if (cropRes?.result?.error || yieldRes?.result?.error || seedRes?.result?.error) {
        throw new ApiError(
          cropRes?.result?.error || yieldRes?.result?.error || seedRes?.result?.error || "",
          200,
        );
      }
      const outcome = vqcOutcome(vqc);
      setFallback({
        cropClassical: cropRes.result.classical,
        cropQuantum: cropRes.result.quantum,
        yieldClassical: yieldRes.result.classical,
        yieldQuantum: yieldRes.result.quantum,
        seedClassical: seedRes.result.classical,
        seedQuantum: seedRes.result.quantum,
        vqcProbability: outcome.probability,
        vqcFavourable: outcome.favourable,
        backendNote,
      });
    },
    [n, p, k, temp, hum, rain, crop, season, area, moisture, weight, vqc],
  );

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      // The backend /api/quantum-ml endpoint parses request.form values.
      const form = new FormData();
      form.append("nitrogen", String(n));
      form.append("phosphorus", String(p));
      form.append("potassium", String(k));
      form.append("temperature", String(temp));
      form.append("humidity", String(hum));
      form.append("ph", String(ph));
      form.append("rainfall", String(rain));
      form.append("crop", crop);
      // `season` is intentionally omitted: the yield leg has no season input.
      form.append("area_hectares", String(area));
      form.append("moisture", String(moisture));
      form.append("weight", String(weight));

      let backendNote = "";
      try {
        const res = await api<QuantumMLResponse>("/api/quantum-ml", { method: "POST", formData: form });
        // The backend can signal a model-side failure inside a HTTP 200 body
        // (e.g. its stacked meta-model failing to load). Fall through to the
        // per-module path instead of leaving the screen broken.
        if (res?.result && !res.result.error) {
          setFallback(null);
          setData(res);
          return;
        }
        backendNote = res?.result?.error || "quantum-ml unavailable";
      } catch (e) {
        backendNote = e instanceof ApiError || e instanceof NetworkError ? e.message : "quantum-ml unavailable";
      }

      // Fallback: the classical/VQC module endpoints each work on their own, and
      // the variational circuit is simulated on the device. Nothing is invented —
      // the aggregated score simply is not available while the stack is broken.
      setData(null);
      await loadFallback(backendNote);
    } catch (e) {
      setData(null);
      setFallback(null);
      setErrorMsg(
        e instanceof ApiError || e instanceof NetworkError
          ? e.message
          : t("errors.simulationFailed"),
      );
    } finally {
      setIsPredicting(false);
    }
  };

  const fallbackShare = fallback
    ? [
        t("share.quantumTitle"),
        t("share.quantumProbability", { value: (fallback.vqcProbability * 100).toFixed(1) }),
        t("share.quantumDecision", {
          value: fallback.vqcFavourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal"),
        }),
        "",
        t("share.quantumCropRf", { value: fallback.cropClassical }),
        t("share.quantumCropVqc", { value: fallback.cropQuantum }),
        t("share.quantumYieldXgb", { value: fallback.yieldClassical }),
        t("share.quantumYieldVqr", { value: fallback.yieldQuantum ?? t("common.unavailable") }),
        t("share.quantumSeedSvm", { value: fallback.seedClassical }),
        t("share.quantumSeedVqc", { value: fallback.seedQuantum }),
      ].join("\n")
    : null;

  const shareText = data
    ? [
        t("share.quantumTitle"),
        t("share.quantumProbability", { value: data.result.prob_success }),
        t("share.quantumDecision", { value: data.result.decision }),
        "",
        t("share.quantumCropRf", { value: data.result.crop_rf }),
        t("share.quantumCropVqc", { value: data.result.crop_vqc }),
        t("share.quantumYieldXgb", { value: data.result.yield_xgb }),
        t("share.quantumYieldVqr", { value: data.result.yield_vqr }),
        t("share.quantumSeedSvm", { value: data.result.seed_svm }),
        t("share.quantumSeedVqc", { value: data.result.seed_vqc }),
      ].join("\n")
    : fallbackShare;

  const reportData: ReportData | null = data
    ? {
        title: t("report.quantumTitle"),
        domain: t("report.domainQuantum"),
        primaryResult: {
          label: t("report.probabilityLabel"),
          value: `${data.result.prob_success}%`,
          subtext: data.result.decision,
        },
        parameters: [
          { label: t("report.parametersNitrogen"), value: `${n} mg/kg` },
          { label: t("report.parametersPhosphorus"), value: `${p} mg/kg` },
          { label: t("report.parametersPotassium"), value: `${k} mg/kg` },
          { label: t("report.parametersTemperature"), value: `${temp} °C` },
          { label: t("report.parametersHumidity"), value: `${hum} %` },
          { label: t("report.parametersRainfall"), value: `${rain} mm` },
          { label: t("report.parametersPh"), value: `${ph}` },
          { label: t("report.parametersCropYield"), value: crop },
          { label: t("report.parametersSeason"), value: season },
          { label: t("report.parametersArea"), value: `${area} ha` },
          { label: t("report.parametersMoisture"), value: `${moisture} %` },
          { label: t("report.parametersSeedWeight"), value: `${weight} g` },
        ],
        models: [
          { model: t("report.modelCropRf"), prediction: data.result.crop_rf },
          { model: t("report.modelCropVqc"), prediction: data.result.crop_vqc },
          { model: t("report.modelYieldXgb"), prediction: `${data.result.yield_xgb} t/ha` },
          { model: t("report.modelYieldVqr"), prediction: `${data.result.yield_vqr} t/ha` },
          { model: t("report.modelSeedSvm"), prediction: data.result.seed_svm },
          { model: t("report.modelSeedVqc"), prediction: data.result.seed_vqc },
        ],
        summaryNotes: t("report.quantumSummaryNotes", {
          probability: data.result.prob_success,
          decision: data.result.decision,
        }),
      }
    : fallback
      ? {
          title: t("report.quantumTitle"),
          domain: t("report.domainQuantum"),
          primaryResult: {
            label: t("quantumLabs.successProbability"),
            value: `${(fallback.vqcProbability * 100).toFixed(1)}%`,
            subtext: fallback.vqcFavourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal"),
          },
          parameters: [
            { label: t("report.parametersNitrogen"), value: `${n} mg/kg` },
            { label: t("report.parametersPhosphorus"), value: `${p} mg/kg` },
            { label: t("report.parametersPotassium"), value: `${k} mg/kg` },
            { label: t("report.parametersTemperature"), value: `${temp} °C` },
            { label: t("report.parametersHumidity"), value: `${hum} %` },
            { label: t("report.parametersRainfall"), value: `${rain} mm` },
            { label: t("report.parametersPh"), value: `${ph}` },
            { label: t("report.parametersCropYield"), value: crop },
            { label: t("report.parametersSeason"), value: season },
            { label: t("report.parametersArea"), value: `${area} ha` },
            { label: t("report.parametersMoisture"), value: `${moisture} %` },
            { label: t("report.parametersSeedWeight"), value: `${weight} g` },
          ],
          models: [
            { model: t("report.modelCropRf"), prediction: fallback.cropClassical },
            { model: t("report.modelCropVqc"), prediction: fallback.cropQuantum },
            { model: t("report.modelYieldXgb"), prediction: `${fallback.yieldClassical} t/ha` },
            { model: t("report.modelYieldVqr"), prediction: fallback.yieldQuantum === null ? t("common.unavailable") : `${fallback.yieldQuantum} t/ha` },
            { model: t("report.modelSeedSvm"), prediction: fallback.seedClassical },
            { model: t("report.modelSeedVqc"), prediction: fallback.seedQuantum },
          ],
          summaryNotes: t("report.quantumSummaryNotes", {
            probability: (fallback.vqcProbability * 100).toFixed(1),
            decision: fallback.vqcFavourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal"),
          }),
        }
      : null;

  return (
    <AiScreenShell
      title={t("quantum.title")}
      subtitle={t("quantum.subtitle")}
      isPredicting={isPredicting}
      onPredict={handlePredict}
      onRetry={handlePredict}
      error={errorMsg}
      result={data ? <QuantumResult data={data} /> : fallback ? <FallbackResult data={fallback} /> : null}
      shareText={shareText}
      reportData={reportData}
      predictLabel={t("quantum.predict")}
    >
      {/* The interactive circuit lives in Quantum Labs; this screen is the
          prediction stack. Both share the same simulator. */}
      <Pressable onPress={() => router.push("/quantum-labs")}>
        <Card style={styles.labsCard}>
          <View style={styles.labsRow}>
            <Atom size={22} color={theme.colors.mint} />
            <View style={{ flex: 1 }}>
              <Text style={styles.labsTitle}>{t("quantumLabs.title")}</Text>
              <Text style={styles.labsSubtitle}>{t("quantumLabs.subtitle")}</Text>
            </View>
            <ArrowRight size={18} color={theme.colors.sage} />
          </View>
        </Card>
      </Pressable>

      <Text style={styles.sectionLabel}>{t("quantum.cropInputs")}</Text>
      <SliderField label={t("quantum.nLabel")} value={n} onValueChange={setN} min={0} max={140} unit="mg/kg" optimal={[60, 100]} />
      <SliderField label={t("quantum.pLabel")} value={p} onValueChange={setP} min={0} max={140} unit="mg/kg" optimal={[30, 60]} />
      <SliderField label={t("quantum.kLabel")} value={k} onValueChange={setK} min={0} max={200} unit="mg/kg" optimal={[40, 80]} />
      <SliderField label={t("quantum.temperatureLabel")} value={temp} onValueChange={setTemp} min={0} max={50} step={0.1} unit="°C" optimal={[18, 30]} />
      <SliderField label={t("quantum.humidityLabel")} value={hum} onValueChange={setHum} min={0} max={100} step={0.1} unit="%" optimal={[40, 70]} />
      <SliderField label={t("quantum.rainfallLabel")} value={rain} onValueChange={setRain} min={0} max={300} step={0.5} unit="mm" optimal={[80, 200]} />
      <SliderField label={t("quantum.phLabel")} value={ph} onValueChange={setPh} min={0} max={14} step={0.1} unit="pH" optimal={[6.0, 7.5]} />

      <Text style={styles.sectionLabel}>{t("quantum.yieldInputs")}</Text>
      <PickerField label={t("quantum.cropLabel")} value={crop} onValueChange={setCrop} items={CROPS} />
      <PickerField
        label={t("quantum.seasonLabel")}
        value={season}
        onValueChange={setSeason}
        items={SEASONS}
        hint={t("quantum.seasonNotUsed")}
      />
      <SliderField label={t("quantum.areaLabel")} value={area} onValueChange={setArea} min={1} max={200} unit="ha" />

      <Text style={styles.sectionLabel}>{t("quantum.seedInputs")}</Text>
      <SliderField label={t("quantum.moistureLabel")} value={moisture} onValueChange={setMoisture} min={5} max={25} step={0.1} unit="%" optimal={[10, 13.5]} />
      <SliderField label={t("quantum.weightLabel")} value={weight} onValueChange={setWeight} min={10} max={100} step={0.5} unit="g" optimal={[45, 70]} />
    </AiScreenShell>
  );
}

function QuantumResult({ data }: { data: QuantumMLResponse }) {
  const { t } = useI18n();
  const r = data.result;
  const optimal = r.prob_success >= 50;
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("quantum.resultHeading")}</ResultHeading>

      <Card style={styles.resultCard}>
        <Text style={styles.resultLabel}>{t("quantum.successProbability")}</Text>
        <Text style={[styles.resultValue, { color: optimal ? theme.colors.success : theme.colors.warning }]}>
          {r.prob_success}%
        </Text>
        <Badge label={r.decision} tone={optimal ? "success" : "warning"} />
        <View style={{ width: "100%", marginTop: theme.spacing.md }}>
          <ProgressBar value={r.prob_success} tone={optimal ? "success" : "warning"} />
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("quantum.componentPredictions")}</Text>
        <Row label={t("quantum.cropRfRow")} value={r.crop_rf} />
        <Row label={t("quantum.cropVqcRow")} value={r.crop_vqc} />
        <Row label={t("quantum.yieldXgbRow")} value={`${r.yield_xgb} t/ha`} />
        <Row label={t("quantum.yieldVqrRow")} value={`${r.yield_vqr} t/ha`} />
        <Row label={t("quantum.seedSvmRow")} value={r.seed_svm} tone={r.seed_svm === "Viable" ? "success" : "danger"} />
        <Row label={t("quantum.seedVqcRow")} value={r.seed_vqc} tone={r.seed_vqc === "Viable" ? "success" : "danger"} />
      </Card>
    </View>
  );
}

function FallbackResult({ data }: { data: FallbackData }) {
  const { t } = useI18n();
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("quantumLabs.vqcResult")}</ResultHeading>

      <Card style={styles.resultCard}>
        <Text style={styles.resultLabel}>{t("quantumLabs.successProbability")}</Text>
        <Text style={[styles.resultValue, { color: data.vqcFavourable ? theme.colors.success : theme.colors.warning }]}>
          {(data.vqcProbability * 100).toFixed(1)}%
        </Text>
        <Badge
          label={data.vqcFavourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal")}
          tone={data.vqcFavourable ? "success" : "warning"}
        />
        <View style={{ width: "100%", marginTop: theme.spacing.md }}>
          <ProgressBar
            value={data.vqcProbability * 100}
            tone={data.vqcFavourable ? "success" : "warning"}
          />
        </View>
        <Text style={styles.noteText}>{data.backendNote}</Text>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("quantum.componentPredictions")}</Text>
        <Row label={t("quantum.cropRfRow")} value={data.cropClassical} />
        <Row label={t("quantum.cropVqcRow")} value={data.cropQuantum} />
        <Row label={t("quantum.yieldXgbRow")} value={`${data.yieldClassical} t/ha`} />
        <Row label={t("quantum.yieldVqrRow")} value={`${data.yieldQuantum} t/ha`} />
        <Row
          label={t("quantum.seedSvmRow")}
          value={data.seedClassical}
          tone={data.seedClassical === "Viable" ? "success" : "danger"}
        />
        <Row
          label={t("quantum.seedVqcRow")}
          value={data.seedQuantum}
          tone={data.seedQuantum === "Viable" ? "success" : "danger"}
        />
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  labsCard: { backgroundColor: theme.colors.feature, borderColor: theme.colors.pine },
  labsRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  labsTitle: { fontSize: 15, fontWeight: "800", color: theme.colors.textInverse },
  labsSubtitle: { fontSize: 11.5, color: theme.colors.sage, marginTop: 1 },
  noteText: { fontSize: 11, color: theme.colors.textMuted, marginTop: theme.spacing.sm, lineHeight: 15 },
  sectionLabel: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.textSecondary,
    textTransform: "uppercase" as const,
    letterSpacing: 0.5,
    marginTop: theme.spacing.xs,
  },
  resultCard: { alignItems: "center" as const, padding: theme.spacing.xl },
  resultLabel: { fontSize: 12, color: theme.colors.textMuted, textTransform: "uppercase" as const, letterSpacing: 1 },
  resultValue: { fontSize: 38, fontWeight: "800" as const, marginTop: 4 },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
});
