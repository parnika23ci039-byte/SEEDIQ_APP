import React, { useState } from "react";
import { Text, View, StyleSheet } from "react-native";
import { ApiError, NetworkError, api } from "@/lib/api";
import { AiScreenShell, ResultHeading } from "@/components/ai-screen";
import { Card, Row, SliderField, PickerField, Badge } from "@/components/ui";
import { CropImage } from "@/components/crop-image";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { CROP_VARIETIES } from "@/lib/crops";
import type { ReportData } from "@/lib/report";
import type { YieldPredictionResponse } from "@/lib/types";

const SEASONS = ["Kharif", "Rabi", "Zaid", "Summer", "Winter", "Autumn", "Spring", "Whole Year"];

export default function YieldAiScreen() {
  const { t } = useI18n();
  const [crop, setCrop] = useState("Rice");
  const [season, setSeason] = useState("Kharif");
  const [area, setArea] = useState(5);

  const [isPredicting, setIsPredicting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [data, setData] = useState<YieldPredictionResponse | null>(null);

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      // Contract: { crop, area_hectares }. `season` is deliberately NOT sent:
      // the served model is trained on annual district-level statistics and has
      // no season input. It stays a local report label below.
      const res = await api<YieldPredictionResponse>("/api/yield-prediction", {
        method: "POST",
        body: { crop, area_hectares: area },
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

  const totalProduction = data ? (data.result.ensemble * area).toFixed(1) : null;

  const shareText = data
    ? [
        t("share.yieldTitle"),
        t("share.yieldSummary", { crop, season, area }),
        t("share.ensembleYield", { value: data.result.ensemble }),
        t("share.classicalXgb", { value: data.result.classical }),
        t("share.quantumVqr", { value: data.result.quantum }),
        totalProduction ? t("share.totalProduction", { value: totalProduction }) : "",
        "",
        t("share.marketAnalysis"),
        t("share.pricePerTonneShare", { value: data.market_analysis.price_per_tonne }),
        t("share.grossRevenueShare", { value: data.market_analysis.gross_revenue }),
        t("share.totalCostShare", { value: data.market_analysis.total_cost }),
        t("share.netProfitShare", { value: data.market_analysis.net_profit }),
        t("share.demandTrendShare", {
          demand: data.market_analysis.demand,
          trend: data.market_analysis.trend,
        }),
      ]
        .filter(Boolean)
        .join("\n")
    : null;

  const reportData: ReportData | null = data
    ? {
        title: t("report.yieldTitle", { crop }),
        domain: t("report.domainYield"),
        primaryResult: {
          label: t("report.expectedYieldLabel"),
          value: `${data.result.ensemble} t/ha`,
          subtext:
            data.result.error ||
            t("report.expectedYieldSubtext", { total: totalProduction, area, season }),
        },
        parameters: [
          { label: t("report.parametersCrop"), value: crop },
          { label: t("report.parametersSeason"), value: season },
          { label: t("report.parametersArea"), value: `${area} ha` },
          { label: t("report.parametersTotal"), value: `${totalProduction} tons` },
        ],
        models: [
          { model: t("report.modelXgb"), prediction: `${data.result.classical} t/ha` },
          ...(data.result.quantum != null
            ? [{
                model: t("report.modelQuantumVqr"),
                prediction: `${data.result.quantum} t/ha`,
              }]
            : []),
          { model: t("report.modelEnsembleForecast"), prediction: `${data.result.ensemble} t/ha` },
        ],
        advisories: [
          {
            title: t("report.advisoryMarketPrice"),
            desc: t("report.advisoryMarketPriceDesc", {
              value: data.market_analysis.price_per_tonne,
            }),
            priority: data.market_analysis.demand ?? undefined,
          },
          {
            title: t("report.advisoryGrossRevenue"),
            desc: data.market_analysis.gross_revenue ?? t("common.unavailable"),
          },
          {
            title: t("report.advisoryTotalCost"),
            desc: data.market_analysis.total_cost ?? t("common.unavailable"),
          },
          {
            title: t("report.advisoryNetProfit"),
            desc: t("report.advisoryNetProfitDesc", {
              value: data.market_analysis.net_profit,
              state: t(
                data.market_analysis.profit_sign === 1
                  ? "report.advisoryProfitable"
                  : "report.advisoryNegative",
              ),
            }),
            priority: t(
              data.market_analysis.profit_sign === 1
                ? "report.advisoryRiskPositive"
                : "report.advisoryRiskAtRisk",
            ),
          },
          {
            title: t("report.advisoryPriceTrend"),
            desc: data.market_analysis.trend ?? t("common.unavailable"),
          },
        ],
      }
    : null;

  return (
    <AiScreenShell
      title={t("yieldAi.title")}
      subtitle={t("yieldAi.subtitle")}
      isPredicting={isPredicting}
      onPredict={handlePredict}
      onRetry={handlePredict}
      error={errorMsg}
      result={data ? <YieldResult data={data} crop={crop} season={season} area={area} /> : null}
      shareText={shareText}
      reportData={reportData}
      predictLabel={t("yieldAi.predict")}
    >
      <PickerField label={t("yieldAi.cropLabel")} value={crop} onValueChange={setCrop} items={CROP_VARIETIES} />
      <PickerField
        label={t("yieldAi.seasonLabel")}
        value={season}
        onValueChange={setSeason}
        items={SEASONS}
        hint={t("yieldAi.seasonNotUsed")}
      />
      <SliderField label={t("yieldAi.areaLabel")} value={area} onValueChange={setArea} min={1} max={200} unit="ha" hint={t("yieldAi.areaHint")} />
    </AiScreenShell>
  );
}

function YieldResult({
  data,
  crop,
  season,
  area,
}: {
  data: YieldPredictionResponse;
  crop: string;
  season: string;
  area: number;
}) {
  const { t } = useI18n();
  const total = (data.result.ensemble * area).toFixed(1);
  const profitable = data.market_analysis.profit_sign === 1;
  return (
    <View style={{ gap: theme.spacing.md }}>
      <ResultHeading>{t("yieldAi.resultHeading")}</ResultHeading>

      {/* Original SeedIQ crop + storage imagery for the selected crop */}
      <View style={styles.imageRow}>
        <CropImage crop={crop} kind="crop" height={140} label={crop} style={styles.imageHalf} />
        <CropImage crop={crop} kind="storage" height={140} label={t("common.storage")} style={styles.imageHalf} />
      </View>

      <Card style={styles.resultCard}>
        <Text style={styles.resultLabel}>{t("yieldAi.expectedYield")}</Text>
        <Text style={styles.resultValue}>
          {data.result.ensemble} <Text style={styles.resultUnit}>t/ha</Text>
        </Text>
        <Text style={styles.totalText}>
          {t("yieldAi.totalAcross", { total, area, crop, season })}
        </Text>
        <View style={styles.modelRow}>
          <Badge label={`${t("yieldAi.classicalBadge")}: ${data.result.classical} t/ha`} tone="info" small />
          {/* The quantum leg is trained on district totals; its per-hectare output
              is unreliable, so it is reported as experimental and is NOT what the
              headline figure above is built from. */}
          {data.result.quantum != null ? (
            <Badge
              label={t("yieldAi.quantumBadgeExperimental", {
                value: `${data.result.quantum} t/ha`,
              })}
              tone="primary"
              small
            />
          ) : null}
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>{t("yieldAi.marketAnalysis")}</Text>
        <Row label={t("yieldAi.pricePerTonne")} value={data.market_analysis.price_per_tonne} />
        <Row label={t("yieldAi.grossRevenue")} value={data.market_analysis.gross_revenue} />
        <Row label={t("yieldAi.totalCost")} value={data.market_analysis.total_cost} />
        <Row
          label={t("yieldAi.netProfit")}
          value={data.market_analysis.net_profit}
          tone={profitable ? "success" : "danger"}
        />
        <Row label={t("yieldAi.demand")} value={data.market_analysis.demand} />
        <Row label={t("yieldAi.priceTrend")} value={data.market_analysis.trend} />
      </Card>

      {data.crops?.length > 0 && (
        <Card>
          <Text style={styles.cardTitle}>{t("yieldAi.supportedCrops")}</Text>
          <Text style={styles.adviceText}>{data.crops.join(", ")}</Text>
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  imageRow: { flexDirection: "row" as const, gap: theme.spacing.sm },
  imageHalf: { flex: 1, height: 140 },
  resultCard: { alignItems: "center" as const, padding: theme.spacing.xl },
  resultLabel: { fontSize: 12, color: theme.colors.textMuted, textTransform: "uppercase" as const, letterSpacing: 1 },
  resultValue: { fontSize: 34, fontWeight: "800" as const, color: theme.colors.primary, marginTop: 4 },
  resultUnit: { fontSize: 16, fontWeight: "600" as const, color: theme.colors.textSecondary },
  totalText: { fontSize: 13, color: theme.colors.textSecondary, marginTop: 6, textAlign: "center" as const },
  modelRow: { flexDirection: "row" as const, gap: 8, marginTop: theme.spacing.md, flexWrap: "wrap" as const, justifyContent: "center" as const },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text, marginBottom: 4 },
  adviceText: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 18 },
});
