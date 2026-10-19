import React, { useMemo, useRef, useState } from "react";
import { PanResponder, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, G, Path, Rect, Text as SvgText } from "react-native-svg";
import { theme } from "../theme/theme";
import { KARNATAKA_DISTRICTS, KARNATAKA_VIEWBOX, normalizeDistrictName } from "../lib/karnataka-geo";

export type RiskLevel = "CRITICAL" | "WARNING" | "MONITOR" | "STABLE";

const RISK_FILL: Record<RiskLevel, string> = {
  CRITICAL: theme.colors.riskCritical,
  WARNING: theme.colors.riskWarning,
  MONITOR: theme.colors.riskMonitor,
  STABLE: theme.colors.riskStable,
};

const NO_DATA_FILL = theme.colors.surfaceMuted;

const VB_W = KARNATAKA_VIEWBOX.width;
const VB_H = KARNATAKA_VIEWBOX.height;

export interface DistrictRisk {
  risk: RiskLevel;
  /** Optional short label drawn next to the marker (e.g. "62%"). */
  badge?: string;
}

interface Props {
  /** Risk per district, keyed by any spelling of the district name. */
  risks?: Record<string, DistrictRisk>;
  selected?: string | null;
  onSelectDistrict?: (name: string) => void;
  showLabels?: boolean;
  showRisk?: boolean;
  height?: number;
  /** Externally driven zoom (1 = whole state). */
  zoom?: number;
}

function ringPath(rings: [number, number][][]): string {
  let d = "";
  for (const ring of rings) {
    d += `M${ring[0][0]},${ring[0][1]}`;
    for (let i = 1; i < ring.length; i++) d += `L${ring[i][0]},${ring[i][1]}`;
    d += "Z";
  }
  return d;
}

/** Ray-casting point-in-polygon test in map (viewBox) coordinates. */
function pointInRing(px: number, py: number, ring: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/**
 * District under a map point.
 *
 * `Path`-level `onPress` from react-native-svg is unreliable on Android under
 * the New Architecture (software-mansion/react-native-svg#2796, Expo SDK 54), so
 * taps are resolved here against the same polygons that are drawn.
 */
function districtAtPoint(x: number, y: number): string | null {
  for (const d of KARNATAKA_DISTRICTS) {
    if (d.rings.some((ring) => pointInRing(x, y, ring))) return d.name;
  }
  return null;
}

/**
 * Karnataka district map.
 *
 * Renders the real district boundaries (pre-projected at build time, see
 * `src/lib/karnataka-geo.ts`) as SVG polygons, with drag-to-pan and
 * button/step zoom. Colours and markers come from live backend telemetry — the
 * map invents no data: a district with no telemetry is drawn neutral.
 */
export function KarnatakaMap({
  risks = {},
  selected,
  onSelectDistrict,
  showLabels = true,
  showRisk = true,
  height = 420,
}: Props) {
  const [layout, setLayout] = useState({ width: 0, height });
  const [view, setView] = useState({ x: 0, y: 0, w: VB_W, h: VB_H });
  const viewRef = useRef(view);
  viewRef.current = view;

  // `zoom` in the public API is expressed as a step count from the full view.
  const [, setStep] = useState(0);
  const stepRef = useRef(0);

  const applyZoom = (next: number) => {
    const clamped = Math.min(4, Math.max(1, next));
    stepRef.current = clamped;
    setStep(clamped);
    const w = VB_W / clamped;
    const h = VB_H / clamped;
    setView({ x: (VB_W - w) / 2, y: (VB_H - h) / 2, w, h });
  };

  const panStart = useRef({ x: 0, y: 0 });

  // Taps are resolved at view level so district selection does not depend on
  // react-native-svg shape press handling (broken on Android/Fabric, see above).
  const layoutRef = useRef(layout);
  layoutRef.current = layout;
  const onSelectRef = useRef(onSelectDistrict);
  onSelectRef.current = onSelectDistrict;

  /**
   * Map a canvas-local touch point to a district and select it.
   *
   * Taps are resolved against the same polygons that are drawn, because
   * `Path`-level `onPress` from react-native-svg is unreliable on Android under
   * the New Architecture (software-mansion/react-native-svg#2796, Expo SDK 54):
   * it never fires on device, which left the district detail panel unreachable.
   */
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const tapAt = (locationX: number, locationY: number) => {
    const { width, height } = layoutRef.current;
    const v = viewRef.current;
    if (!width || !height) return;
    // `preserveAspectRatio="xMidYMid meet"` letterboxes the viewBox inside the canvas.
    const s = Math.min(width / v.w, height / v.h);
    const x = v.x + (locationX - (width - v.w * s) / 2) / s;
    const y = v.y + (locationY - (height - v.h * s) / 2) / s;
    if (x < v.x || y < v.y || x > v.x + v.w || y > v.y + v.h) return;
    const name = districtAtPoint(x, y);
    if (name) onSelectRef.current?.(name);
  };

  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => false,
        onMoveShouldSetPanResponder: (_e, g) => Math.abs(g.dx) > 4 || Math.abs(g.dy) > 4,
        onPanResponderGrant: () => {
          panStart.current = { x: viewRef.current.x, y: viewRef.current.y };
        },
        onPanResponderMove: (_e, g) => {
          if (!layoutRef.current.width) return;
          const scale = viewRef.current.w / layoutRef.current.width;
          const nextX = panStart.current.x - g.dx * scale;
          const nextY = panStart.current.y - g.dy * scale;
          setView((v) => ({
            ...v,
            x: Math.min(VB_W - v.w, Math.max(0, nextX)),
            y: Math.min(VB_H - v.h, Math.max(0, nextY)),
          }));
        },
        onPanResponderRelease: () => {
          touchStart.current = null;
        },
      }),
    [],
  );

  const shapes = useMemo(
    () =>
      KARNATAKA_DISTRICTS.map((d) => {
        const key = normalizeDistrictName(d.name);
        const risk = risks[key];
        return {
          name: d.name,
          centroid: d.centroid,
          path: ringPath(d.rings),
          fill: risk && showRisk ? RISK_FILL[risk.risk] ?? NO_DATA_FILL : NO_DATA_FILL,
          risk,
        };
      }),
    [risks, showRisk],
  );

  const markers = shapes.filter((s) => s.risk);
  const hasSelection = !!selected;

  return (
    <View style={styles.wrap}>
      <View
        style={[styles.canvas, { height }]}
        onLayout={(e) =>
          setLayout({
            width: e.nativeEvent.layout.width,
            height: e.nativeEvent.layout.height,
          })
        }
        onTouchStart={(e) => {
          touchStart.current = { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY };
        }}
        onTouchEnd={(e) => {
          const start = touchStart.current;
          touchStart.current = null;
          if (!start) return;
          // Only a touch that stayed put is a tap; a drag pans the map.
          const moved = Math.abs(e.nativeEvent.locationX - start.x) + Math.abs(e.nativeEvent.locationY - start.y);
          if (moved > 12) return;
          tapAt(e.nativeEvent.locationX, e.nativeEvent.locationY);
        }}
        {...responder.panHandlers}
      >
        <Svg
          width="100%"
          height="100%"
          viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
          preserveAspectRatio="xMidYMid meet"
        >
          <Rect x={0} y={0} width={VB_W} height={VB_H} fill={theme.colors.surfaceMuted} opacity={0.35} />
          <G>
            {shapes.map((s) => {
              const isSelected =
                selected && normalizeDistrictName(selected) === normalizeDistrictName(s.name);
              return (
                <Path
                  key={s.name}
                  d={s.path}
                  fill={s.fill}
                  stroke={isSelected ? theme.colors.forest : theme.colors.surface}
                  strokeWidth={isSelected ? 4 : 1}
                  opacity={hasSelection && !isSelected ? 0.72 : 1}
                  onPress={() => onSelectDistrict?.(s.name)}
                />
              );
            })}
          </G>
          <G>
            {markers.map((s) => (
              <Circle
                key={`m-${s.name}`}
                cx={s.centroid[0]}
                cy={s.centroid[1]}
                r={6}
                fill={theme.colors.surface}
                stroke={theme.colors.forest}
                strokeWidth={2}
                opacity={0.95}
              />
            ))}
          </G>
          {showLabels
            ? shapes.map((s) => (
                <SvgText
                  key={`t-${s.name}`}
                  x={s.centroid[0]}
                  y={s.centroid[1] + 22}
                  fontSize={16}
                  fontWeight="600"
                  fill={theme.colors.forest}
                  textAnchor="middle"
                >
                  {s.name}
                </SvgText>
              ))
            : null}
        </Svg>
      </View>

      <View style={styles.controls}>
        <ZoomButton label="+" onPress={() => applyZoom(stepRef.current + 1)} />
        <ZoomButton label="−" onPress={() => applyZoom(stepRef.current - 1)} />
        <ZoomButton label="⌂" onPress={() => applyZoom(1)} />
      </View>

    </View>
  );
}

function ZoomButton({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Text onPress={onPress} style={styles.zoomBtn} accessibilityRole="button">
      {label}
    </Text>
  );
}

/** Legend swatches, exported so the screen can render it next to the map. */
export function mapLegend(): { level: RiskLevel; color: string }[] {
  return (Object.keys(RISK_FILL) as RiskLevel[]).map((level) => ({
    level,
    color: RISK_FILL[level],
  }));
}

const styles = StyleSheet.create({
  wrap: { position: "relative" },
  canvas: {
    width: "100%",
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  controls: {
    position: "absolute",
    right: theme.spacing.md,
    top: theme.spacing.md,
    gap: 6,
  },
  zoomBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    textAlign: "center",
    textAlignVertical: "center",
    lineHeight: 36,
    fontSize: 20,
    fontWeight: "800",
    color: theme.colors.textInverse,
    backgroundColor: theme.colors.primary,
    overflow: "hidden",
  },
});
