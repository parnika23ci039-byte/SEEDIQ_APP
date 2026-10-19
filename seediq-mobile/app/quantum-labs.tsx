import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, Atom, Play, RotateCcw, Cpu, Zap } from "lucide-react-native";
import Svg, { Circle, Line } from "react-native-svg";
import { Badge, Button, Card, ProgressBar, Row, SliderField } from "@/components/ui";
import { useI18n } from "@/i18n";
import { theme } from "@/theme/theme";
import { STATUS_BAR_TOP } from "@/lib/layout";
import {
  AgronomicFeatures,
  BASIS_LABELS,
  CircuitAngles,
  SimulationResult,
  encodeFeatures,
  encodeSoilParameters,
  encodingBreakdown,
  simulate,
  vqcOutcome,
} from "@/lib/quantum";

const DEG = 180 / Math.PI;
const RAD = Math.PI / 180;

const DEFAULT_FEATURES: AgronomicFeatures = {
  nitrogen: 90,
  phosphorus: 42,
  potassium: 43,
  temperature: 24.5,
  humidity: 62,
  ph: 6.5,
  rainfall: 102.5,
  moisture: 10.5,
  weight: 42.5,
};

// The four soil inputs of the website's control panel. They are angle-encoded
// into the same circuit, so the read-out below responds to them directly.
const DEFAULT_SOIL = { nitrogen: 90, phosphorus: 42, potassium: 43, ph: 6.5 };

/**
 * Quantum Labs.
 *
 * Two things live here, both driven by the same circuit:
 *   • Quantum Playground — every gate angle is editable and the circuit is
 *     drawn as |q0> / |q1> wires with Ry, H, Rz, M columns.
 *   • Live VQC simulation — the agronomic features angle-encode into the same
 *     circuit and the read-out updates from the simulated state.
 *
 * The state vector, probabilities and shot histogram are all produced by
 * `src/lib/quantum.ts`, a real state-vector simulator — nothing here is a
 * screenshot or a canned number.
 */
export default function QuantumLabsScreen() {
  const router = useRouter();
  const { t } = useI18n();

  const [features, setFeatures] = useState<AgronomicFeatures>(DEFAULT_FEATURES);
  const [soil, setSoil] = useState(DEFAULT_SOIL);
  const [angles, setAngles] = useState<CircuitAngles>(() => encodeFeatures(DEFAULT_FEATURES));
  const [result, setResult] = useState<SimulationResult | null>(() => simulate(encodeFeatures(DEFAULT_FEATURES)));
  const [running, setRunning] = useState(false);
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);
  const [showFeatures, setShowFeatures] = useState(false);

  const run = useCallback((next: CircuitAngles) => {
    setRunning(true);
    // One frame of feedback, then the (synchronous) simulation.
    requestAnimationFrame(() => {
      setResult(simulate(next));
      setRunning(false);
      setLastRunAt(new Date());
    });
  }, []);

  // Live mode: re-run whenever a gate angle changes, so the read-out is never
  // stale. (The button stays as an explicit run/re-run affordance.)
  useEffect(() => {
    const id = setTimeout(() => run(angles), 120);
    return () => clearTimeout(id);
  }, [angles, run]);

  const setAngle = (key: "ry0" | "ry1" | "rz0" | "rz1", valueRadians: number) => {
    setAngles((prev) => ({ ...prev, [key]: valueRadians }));
  };

  const setEntangle = (value: boolean) => {
    setAngles((prev) => ({ ...prev, entangle: value }));
  };

  const reEncode = () => setAngles(encodeFeatures(features));

  // "Calculate Ansatz" — the website's primary control: the four soil
  // parameters are angle-encoded and the circuit is re-run on the encoded state.
  const calculateAnsatz = () => {
    const next = encodeSoilParameters(soil.nitrogen, soil.phosphorus, soil.potassium, soil.ph);
    setAngles(next);
    run(next);
  };

  const reset = () => {
    setFeatures(DEFAULT_FEATURES);
    setSoil(DEFAULT_SOIL);
    setAngles(encodeFeatures(DEFAULT_FEATURES));
  };

  const outcome = useMemo(() => (result ? vqcOutcome(result) : null), [result]);
  const encoding = useMemo(() => encodingBreakdown(features), [features]);

  const gateCells = [
    { key: "ry", label: "Ry" },
    { key: "h", label: "H" },
    { key: "rz", label: "Rz" },
    { key: "m", label: "M" },
  ];

  return (
    <View style={styles.fill}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <ArrowLeft size={20} color={theme.colors.textInverse} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.topTitle}>{t("quantumLabs.title")}</Text>
          <Text style={styles.topSubtitle}>{t("quantumLabs.subtitle")}</Text>
        </View>
        <Atom size={22} color={theme.colors.sage} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {/* ---------------------------------------------------------- circuit */}
        <Card style={styles.circuitCard}>
          <View style={styles.circuitHead}>
            <Text style={styles.cardTitle}>{t("quantumLabs.circuitTitle")}</Text>
            <Badge
              label={`${t("quantumLabs.depth")} ${result?.depth ?? "-"}`}
              tone="primary"
              small
            />
          </View>

          <View style={styles.grid}>
            <View style={styles.labelCol}>
              <View style={styles.cell}>
                <Text style={styles.qubitLabel}>|q₀⟩</Text>
              </View>
              <View style={styles.cell}>
                <Text style={styles.qubitLabel}>|q₁⟩</Text>
              </View>
            </View>

            {gateCells.map((g) => (
              <View key={g.key} style={styles.gateCol}>
                <View style={styles.cell}>
                  <View style={styles.wire} />
                  <View style={[styles.gate, g.key === "m" && styles.gateMeasure]}>
                    <Text style={styles.gateText}>{g.label}</Text>
                  </View>
                </View>
                <View style={styles.cell}>
                  <View style={styles.wire} />
                  <View style={[styles.gate, g.key === "m" && styles.gateMeasure]}>
                    <Text style={styles.gateText}>{g.label}</Text>
                  </View>
                </View>
              </View>
            ))}

            {angles.entangle ? (
              <View style={styles.gateCol}>
                <View style={styles.cell}>
                  <View style={styles.wire} />
                  <View style={styles.controlDot} />
                </View>
                <View style={styles.cell}>
                  <View style={styles.wire} />
                  <View style={styles.connector} />
                  <View style={styles.targetRing}>
                    <Text style={styles.targetText}>⊕</Text>
                  </View>
                </View>
              </View>
            ) : null}
          </View>

          <View style={styles.legendRow}>
            <Text style={styles.legendText}>{t("quantumLabs.descRy")}</Text>
            <Text style={styles.legendText}>{t("quantumLabs.descH")}</Text>
            <Text style={styles.legendText}>{t("quantumLabs.descRz")}</Text>
            <Text style={styles.legendText}>{t("quantumLabs.descM")}</Text>
          </View>

          <View style={styles.entangleRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.inputLabel}>{t("quantumLabs.entanglement")}</Text>
              <Text style={styles.hint}>{t("quantumLabs.entanglementHint")}</Text>
            </View>
            <Switch
              value={angles.entangle}
              onValueChange={setEntangle}
              trackColor={{ false: theme.colors.surfaceMuted, true: theme.colors.primary }}
              thumbColor={theme.colors.surface}
            />
          </View>
        </Card>

        {/* --------------------------------------------- input parameters */}
        {/* Website parity: the four soil parameters are the playground's inputs
            and are angle-encoded into the circuit by Calculate Ansatz. */}
        <Text style={styles.sectionLabel}>{t("quantumLabs.inputParams")}</Text>
        <Text style={styles.hint}>{t("quantumLabs.inputParamsHint")}</Text>
        <Card>
          <SliderField
            label={t("quantumLabs.nitrogen")}
            value={soil.nitrogen}
            onValueChange={(v) => setSoil((s) => ({ ...s, nitrogen: v }))}
            min={0}
            max={140}
            unit="kg/ha"
            optimal={[60, 100]}
          />
          <SliderField
            label={t("quantumLabs.phosphorus")}
            value={soil.phosphorus}
            onValueChange={(v) => setSoil((s) => ({ ...s, phosphorus: v }))}
            min={0}
            max={140}
            unit="kg/ha"
            optimal={[30, 60]}
          />
          <SliderField
            label={t("quantumLabs.potassium")}
            value={soil.potassium}
            onValueChange={(v) => setSoil((s) => ({ ...s, potassium: v }))}
            min={0}
            max={205}
            unit="kg/ha"
            optimal={[120, 200]}
          />
          <SliderField
            label={t("quantumLabs.soilPh")}
            value={soil.ph}
            onValueChange={(v) => setSoil((s) => ({ ...s, ph: v }))}
            min={0}
            max={14}
            step={0.1}
            unit="pH"
            optimal={[6, 7.5]}
          />
          <Button
            label={t("quantumLabs.calculateAnsatz")}
            onPress={calculateAnsatz}
            loading={running}
            icon={<Zap size={16} color={theme.colors.textInverse} />}
          />
          <Text style={styles.hint}>{t("quantumLabs.calculateHint")}</Text>
        </Card>

        {/* ------------------------------------------------------- playground */}
        <Text style={styles.sectionLabel}>{t("quantumLabs.playground")}</Text>
        <Text style={styles.hint}>{t("quantumLabs.playgroundHint")}</Text>

        <SliderField
          label={t("quantumLabs.ryLabel", { qubit: "|q₀⟩" })}
          value={angles.ry0 * DEG}
          onValueChange={(d) => setAngle("ry0", d * RAD)}
          min={0}
          max={360}
          step={1}
          unit="°"
        />
        <SliderField
          label={t("quantumLabs.ryLabel", { qubit: "|q₁⟩" })}
          value={angles.ry1 * DEG}
          onValueChange={(d) => setAngle("ry1", d * RAD)}
          min={0}
          max={360}
          step={1}
          unit="°"
        />
        <SliderField
          label={t("quantumLabs.rzLabel", { qubit: "|q₀⟩" })}
          value={angles.rz0 * DEG}
          onValueChange={(d) => setAngle("rz0", d * RAD)}
          min={0}
          max={360}
          step={1}
          unit="°"
        />
        <SliderField
          label={t("quantumLabs.rzLabel", { qubit: "|q₁⟩" })}
          value={angles.rz1 * DEG}
          onValueChange={(d) => setAngle("rz1", d * RAD)}
          min={0}
          max={360}
          step={1}
          unit="°"
        />

        <View style={styles.actionRow}>
          <Button
            label={t("quantumLabs.run")}
            onPress={() => run(angles)}
            loading={running}
            icon={<Play size={16} color={theme.colors.textInverse} />}
            style={{ flex: 1 }}
          />
          <Button
            label={t("quantumLabs.reset")}
            variant="outline"
            onPress={reset}
            icon={<RotateCcw size={16} color={theme.colors.primary} />}
            style={{ flex: 1 }}
          />
        </View>
        <Text style={styles.dirty}>
          {lastRunAt ? new Date(lastRunAt).toLocaleTimeString() : ""}
        </Text>

        {/* ------------------------------------------------ live VQC read-out */}
        <Text style={styles.sectionLabel}>{t("quantumLabs.vqcTitle")}</Text>
        <Text style={styles.hint}>{t("quantumLabs.vqcHint")}</Text>

        <Card style={styles.resultCard}>
          <Text style={styles.resultLabel}>{t("quantumLabs.successProbability")}</Text>
          <Text style={[styles.resultValue, { color: outcome?.favourable ? theme.colors.success : theme.colors.warning }]}>
            {outcome ? `${(outcome.probability * 100).toFixed(1)}%` : "--"}
          </Text>
          {outcome ? (
            <Badge
              label={outcome.favourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal")}
              tone={outcome.favourable ? "success" : "warning"}
            />
          ) : null}
          <View style={{ width: "100%", marginTop: theme.spacing.md }}>
            <ProgressBar
              value={(outcome?.probability ?? 0) * 100}
              tone={outcome?.favourable ? "success" : "warning"}
            />
          </View>
          <View style={{ width: "100%", marginTop: theme.spacing.sm }}>
            <Row label={`P(|q₀⟩ = 1)`} value={(result?.probQubit0 ?? 0).toFixed(4)} />
            <Row label={`P(|q₁⟩ = 1)`} value={(result?.probQubit1 ?? 0).toFixed(4)} />
            <Row
              label={t("quantumLabs.decision")}
              value={outcome?.favourable ? t("quantumLabs.optimal") : t("quantumLabs.suboptimal")}
              tone={outcome?.favourable ? "success" : "warning"}
            />
            <Row label={t("quantumLabs.gates")} value={String(result?.gateCount ?? "-")} />
            <Row
              label={t("quantumLabs.depth")}
              value={`${result?.depth ?? "-"} · ${lastRunAt ? lastRunAt.toLocaleTimeString() : "-"}`}
            />
          </View>
        </Card>

        {/* ---------------------------------------- match probability gauge */}
        <Card style={styles.gaugeCard}>
          <Text style={styles.cardTitle}>{t("quantumLabs.matchProbability")}</Text>
          <QuantumGauge
            value={outcome?.probability ?? 0}
            color={outcome?.favourable ? theme.colors.primary : theme.colors.accent}
            label={outcome ? `${(outcome.probability * 100).toFixed(1)}%` : "--"}
          />
          <Text style={styles.hint}>{t("quantumLabs.matchProbabilityHint")}</Text>
        </Card>

        {/* ---------------------------------------------------- telemetry */}
        {/* Every bar is derived from the simulated state vector: read-out
            fidelity, Schmidt entanglement entropy and the distribution's
            normalised Shannon entropy (expressibility). */}
        <Card>
          <Text style={styles.cardTitle}>{t("quantumLabs.telemetry")}</Text>
          <MetricBar
            label={t("quantumLabs.readoutFidelity")}
            value={result?.fidelity ?? 0}
            color={theme.colors.primary}
          />
          <MetricBar
            label={t("quantumLabs.entanglementEntropy")}
            value={result?.entropy ?? 0}
            color={theme.colors.textSecondary}
            suffix={t("quantumLabs.bits")}
          />
          <MetricBar
            label={t("quantumLabs.expressibility")}
            value={result?.expressibility ?? 0}
            color={theme.colors.accent}
          />
        </Card>

        {/* ------------------------------------------- state vector (Bloch) */}
        <Card>
          <Text style={styles.cardTitle}>{t("quantumLabs.stateVisual")}</Text>
          <Text style={styles.hint}>{t("quantumLabs.stateVisualHint")}</Text>
          <View style={styles.blochRow}>
            <BlochProjection
              vector={result?.bloch0 ?? [0, 0, 1]}
              title="|q₀⟩"
            />
            <BlochProjection
              vector={result?.bloch1 ?? [0, 0, 1]}
              title="|q₁⟩"
            />
          </View>
          <View style={styles.psiBox}>
            <Text style={styles.psiText}>
              |ψ⟩ = {result ? result.stateVector.map((a, i) => {
                const mag = Math.sqrt(a.re * a.re + a.im * a.im);
                if (mag < 1e-6) return null;
                return `${mag.toFixed(3)}${BASIS_LABELS[i]}`;
              }).filter(Boolean).join(" + ") : "--"}
            </Text>
          </View>
        </Card>

        {/* ------------------------------------------------- state vector */}
        <Card>
          <Text style={styles.cardTitle}>{t("quantumLabs.stateVector")}</Text>
          <View style={styles.tableHead}>
            <Text style={[styles.th, { flex: 1.1 }]}>{t("quantumLabs.basisState")}</Text>
            <Text style={[styles.th, { flex: 1.5 }]}>{t("quantumLabs.amplitude")}</Text>
            <Text style={[styles.th, { flex: 0.9, textAlign: "right" }]}>
              {t("quantumLabs.probability")}
            </Text>
          </View>
          {BASIS_LABELS.map((label, i) => {
            const amp = result?.stateVector[i];
            const p = result?.probabilities[i] ?? 0;
            const sign = (amp?.im ?? 0) < 0 ? "-" : "+";
            return (
              <View key={label} style={styles.tr}>
                <Text style={[styles.td, styles.tdBasis, { flex: 1.1 }]}>{label}</Text>
                <Text style={[styles.td, { flex: 1.5 }]}>
                  {(amp?.re ?? 0).toFixed(4)} {sign} {(Math.abs(amp?.im ?? 0)).toFixed(4)}i
                </Text>
                <Text style={[styles.td, { flex: 0.9, textAlign: "right" }]}>
                  {(p * 100).toFixed(1)}%
                </Text>
                <View style={styles.trBar}>
                  <ProgressBar value={p * 100} tone={i === (result?.dominantIndex ?? 0) ? "primary" : "info"} />
                </View>
              </View>
            );
          })}
        </Card>

        {/* ----------------------------------------------------- shot counts */}
        <Card>
          <Text style={styles.cardTitle}>{t("quantumLabs.shots")}</Text>
          <Row label={t("quantumLabs.basisState")} value={t("quantumLabs.count")} />
          {BASIS_LABELS.map((label, i) => (
            <View key={label} style={{ marginTop: theme.spacing.sm, gap: 6 }}>
              <Row label={label} value={String(result?.counts[i] ?? 0)} />
              <ProgressBar
                value={((result?.counts[i] ?? 0) / (result?.shots ?? 1024)) * 100}
                tone="primary"
              />
            </View>
          ))}
        </Card>

        {/* ------------------------------------------------------ encoding */}
        <Card>
          <View style={styles.circuitHead}>
            <Text style={styles.cardTitle}>{t("quantumLabs.encoding")}</Text>
            <Cpu size={16} color={theme.colors.primary} />
          </View>
          <Text style={styles.hint}>{t("quantumLabs.vqcHint")}</Text>
          {encoding.map((e) => (
            <Row key={e.label} label={e.label} value={`${e.value} → ${e.angle}`} />
          ))}
          <Pressable onPress={() => setShowFeatures((s) => !s)} hitSlop={8} style={{ marginTop: theme.spacing.sm }}>
            <Text style={styles.link}>
              {t("quantumLabs.agronomicInputs")} {showFeatures ? "▲" : "▼"}
            </Text>
          </Pressable>

          {showFeatures ? (
            <View style={{ gap: theme.spacing.md, marginTop: theme.spacing.md }}>
              <SliderField
                label="Nitrogen"
                value={features.nitrogen}
                onValueChange={(v) => setFeatures((f) => ({ ...f, nitrogen: v }))}
                min={0}
                max={140}
                unit="kg/ha"
                optimal={[60, 100]}
              />
              <SliderField
                label="Soil pH"
                value={features.ph}
                onValueChange={(v) => setFeatures((f) => ({ ...f, ph: v }))}
                min={0}
                max={14}
                step={0.1}
                unit="pH"
                optimal={[6, 7.5]}
              />
              <SliderField
                label="Humidity"
                value={features.humidity}
                onValueChange={(v) => setFeatures((f) => ({ ...f, humidity: v }))}
                min={0}
                max={100}
                unit="%"
                optimal={[40, 70]}
              />
              <SliderField
                label="Seed moisture"
                value={features.moisture}
                onValueChange={(v) => setFeatures((f) => ({ ...f, moisture: v }))}
                min={0}
                max={25}
                step={0.1}
                unit="%"
                optimal={[8, 12]}
              />
              <Button label={t("quantumLabs.reset")} variant="outline" onPress={reEncode} />
            </View>
          ) : null}
        </Card>
      </ScrollView>
    </View>
  );
}

const CELL_HEIGHT = 52;

/**
 * Match-probability gauge drawn from the simulated probability: the arc length
 * is the value itself, so it can never show a number the circuit did not produce.
 */
function QuantumGauge({
  value,
  color,
  label,
  size = 172,
}: {
  value: number;
  color: string;
  label: string;
  size?: number;
}) {
  const stroke = 14;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const clamped = Math.min(1, Math.max(0, value));
  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size}>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={theme.colors.surfaceMuted}
          strokeWidth={stroke}
          fill="none"
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${circumference * clamped} ${circumference}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <View style={styles.gaugeLabelWrap}>
        <Text style={[styles.gaugeLabel, { color }]}>{label}</Text>
      </View>
    </View>
  );
}

/**
 * Bloch-vector projection. The vector comes from the reduced density matrix of
 * the qubit (see blochVector), projected onto the x–z plane with the x–y
 * component's length shown as the shaded ring: a shrunk length means the qubit
 * is entangled with the other one.
 */
function BlochProjection({
  vector,
  title,
  size = 132,
}: {
  vector: [number, number, number];
  title: string;
  size?: number;
}) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 12;
  const [vx, vy, vz] = vector;
  const length = Math.min(1, Math.sqrt(vx * vx + vy * vy + vz * vz));
  const tipX = cx + vx * r;
  const tipY = cy - vz * r;
  return (
    <View style={{ alignItems: "center", gap: 4 }}>
      <Svg width={size} height={size}>
        <Circle cx={cx} cy={cy} r={r} stroke={theme.colors.border} strokeWidth={1.5} fill="none" />
        <Circle cx={cx} cy={cy} r={r * Math.max(0, Math.abs(vz))} stroke={theme.colors.surfaceMuted} strokeWidth={1} fill="none" strokeDasharray="3 3" />
        <Line x1={cx} y1={cy - r} x2={cx} y2={cy + r} stroke={theme.colors.surfaceMuted} strokeWidth={1} strokeDasharray="4 3" />
        <Line x1={cx - r} y1={cy} x2={cx + r} y2={cy} stroke={theme.colors.surfaceMuted} strokeWidth={1} strokeDasharray="4 3" />
        <Line x1={cx} y1={cy} x2={tipX} y2={tipY} stroke={theme.colors.primary} strokeWidth={3} strokeLinecap="round" />
        <Circle cx={tipX} cy={tipY} r={5} fill={theme.colors.primary} />
        <Circle cx={cx} cy={cy} r={2.5} fill={theme.colors.textSecondary} />
      </Svg>
      <Text style={styles.blochTitle}>{title}</Text>
      <Text style={styles.blochMeta}>
        x {vx.toFixed(2)} · z {vz.toFixed(2)} · |r| {length.toFixed(2)}
      </Text>
    </View>
  );
}

/** Telemetry bar — the value is a metric computed from the state vector. */
function MetricBar({
  label,
  value,
  color,
  suffix,
}: {
  label: string;
  value: number;
  color: string;
  suffix?: string;
}) {
  const pct = Math.min(1, Math.max(0, value)) * 100;
  return (
    <View style={{ width: "100%", marginTop: theme.spacing.md, gap: 4 }}>
      <View style={styles.metricHead}>
        <Text style={styles.metricLabel}>{label}</Text>
        <Text style={[styles.metricValue, { color }]}>
          {(value * (suffix ? 1 : 100)).toFixed(suffix ? 3 : 1)}
          {suffix ? ` ${suffix}` : "%"}
        </Text>
      </View>
      <ProgressBar value={pct} tone="primary" />
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

  circuitCard: { backgroundColor: theme.colors.feature, borderColor: theme.colors.pine },
  circuitHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cardTitle: { fontSize: 15, fontWeight: "700", color: theme.colors.text },

  grid: { flexDirection: "row", alignItems: "flex-start", marginTop: theme.spacing.sm },
  labelCol: { justifyContent: "flex-start" },
  gateCol: { flex: 1, alignItems: "center" },
  cell: {
    height: CELL_HEIGHT,
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "stretch",
  },
  wire: {
    position: "absolute",
    left: 0,
    right: 0,
    top: CELL_HEIGHT / 2 - 1,
    height: 2,
    backgroundColor: theme.colors.sage,
    opacity: 0.45,
  },
  qubitLabel: { fontSize: 15, fontWeight: "700", color: theme.colors.textInverse, paddingRight: 8 },
  gate: {
    minWidth: 44,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: theme.colors.primary,
    borderWidth: 1,
    borderColor: theme.colors.sage,
  },
  gateMeasure: { backgroundColor: theme.colors.pine },
  gateText: { color: theme.colors.textInverse, fontWeight: "800", fontSize: 13, textAlign: "center" },
  controlDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: theme.colors.sage,
    borderWidth: 2,
    borderColor: theme.colors.feature,
  },
  connector: {
    position: "absolute",
    top: -CELL_HEIGHT / 2,
    height: CELL_HEIGHT,
    width: 2,
    backgroundColor: theme.colors.sage,
  },
  targetRing: {
    width: 26,
    height: 26,
    borderRadius: 13,
    borderWidth: 2,
    borderColor: theme.colors.sage,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: theme.colors.feature,
  },
  targetText: { color: theme.colors.sage, fontSize: 15, fontWeight: "800", lineHeight: 17 },

  legendRow: { marginTop: theme.spacing.md, gap: 3 },
  legendText: { fontSize: 11, color: theme.colors.sage },

  entangleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.md,
    marginTop: theme.spacing.md,
    borderTopWidth: 1,
    borderTopColor: theme.colors.pine,
    paddingTop: theme.spacing.md,
  },
  inputLabel: { fontSize: 13, fontWeight: "600", color: theme.colors.textInverse },
  hint: { fontSize: 11.5, color: theme.colors.textMuted, lineHeight: 16 },

  sectionLabel: {
    fontSize: 13,
    fontWeight: "700",
    color: theme.colors.textSecondary,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: theme.spacing.sm,
  },
  actionRow: { flexDirection: "row", gap: theme.spacing.md },
  dirty: { fontSize: 11, color: theme.colors.textMuted, textAlign: "center" },

  resultCard: { alignItems: "center", padding: theme.spacing.xl, gap: theme.spacing.sm },
  resultLabel: {
    fontSize: 12,
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  resultValue: { fontSize: 38, fontWeight: "800" },

  tableHead: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: theme.colors.border, paddingBottom: 4 },
  th: { fontSize: 11, fontWeight: "700", color: theme.colors.textMuted, textTransform: "uppercase" },
  tr: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", paddingVertical: 6, gap: 2 },
  td: { fontSize: 12.5, color: theme.colors.text },
  tdBasis: { fontWeight: "700" },
  trBar: { width: "100%", marginTop: 4 },
  link: { fontSize: 13, fontWeight: "700", color: theme.colors.primary },

  gaugeCard: { alignItems: "center", padding: theme.spacing.xl, gap: theme.spacing.md },
  gaugeLabelWrap: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  gaugeLabel: { fontSize: 34, fontWeight: "800" },

  metricHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  metricLabel: { fontSize: 12.5, color: theme.colors.textSecondary, fontWeight: "600" },
  metricValue: { fontSize: 12.5, fontWeight: "700" },

  blochRow: {
    flexDirection: "row",
    justifyContent: "space-around",
    alignItems: "flex-start",
    marginTop: theme.spacing.md,
  },
  blochTitle: { fontSize: 13, fontWeight: "800", color: theme.colors.text },
  blochMeta: { fontSize: 10.5, color: theme.colors.textMuted },
  psiBox: {
    marginTop: theme.spacing.md,
    padding: theme.spacing.md,
    borderRadius: theme.radii.md,
    backgroundColor: theme.colors.featureSoft,
  },
  psiText: { fontSize: 12, color: theme.colors.textSecondary, fontFamily: "monospace" },
});
