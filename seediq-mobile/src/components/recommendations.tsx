import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  NativeScrollEvent,
  NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { useRouter } from "expo-router";
import { Activity, ArrowRight, ShieldCheck, Sprout, TrendingUp } from "lucide-react-native";
import { theme } from "../theme/theme";
import { useI18n, type TranslationKey } from "../i18n";

/**
 * Auto-sliding "AI recommendations" ribbon for the dashboard.
 *
 * The client wanted the AI modules to feel like live recommendations rather
 * than a static list of buttons. This rotates the four real modules on a timer,
 * stays fully tappable, and shows only REAL context (weather / run counts) —
 * no prediction is fabricated here; every number that could look like a result
 * comes from the backend through the caller.
 */

type ModuleHref = "/crop-ai" | "/yield-ai" | "/seed-ai" | "/storage-ai";

const SLIDES: {
  href: ModuleHref;
  title: TranslationKey;
  desc: TranslationKey;
  icon: typeof Sprout;
}[] = [
  { href: "/crop-ai", title: "tools.cropTitle", desc: "tools.cropDesc", icon: Sprout },
  { href: "/yield-ai", title: "tools.yieldTitle", desc: "tools.yieldDesc", icon: TrendingUp },
  { href: "/seed-ai", title: "tools.seedTitle", desc: "tools.seedDesc", icon: Activity },
  { href: "/storage-ai", title: "tools.storageTitle", desc: "tools.storageDesc", icon: ShieldCheck },
];

const AUTO_SLIDE_MS = 4500;
/** After a manual swipe, hold still for a moment before rotating again. */
const RESUME_DELAY_MS = 7000;

export function RecommendationCarousel({ facts = [] }: { facts?: string[] }) {
  const { t } = useI18n();
  const router = useRouter();
  const { width } = useWindowDimensions();

  const cardWidth = Math.max(220, width - theme.spacing.lg * 2);
  const scrollRef = useRef<ScrollView>(null);
  const [index, setIndex] = useState(0);
  const interacting = useRef(false);
  const resumeAt = useRef(0);

  // Rotate while the user is not touching the ribbon.
  useEffect(() => {
    const id = setInterval(() => {
      if (interacting.current || Date.now() < resumeAt.current) return;
      setIndex((i) => (i + 1) % SLIDES.length);
    }, AUTO_SLIDE_MS);
    return () => clearInterval(id);
  }, []);

  // Keep the scroll position in sync with the active index.
  useEffect(() => {
    scrollRef.current?.scrollTo({ x: index * cardWidth, animated: true });
  }, [index, cardWidth]);

  const handleBeginDrag = useCallback(() => {
    interacting.current = true;
  }, []);

  const handleEndDrag = useCallback(() => {
    interacting.current = false;
  }, []);

  const handleMomentumEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      interacting.current = false;
      resumeAt.current = Date.now() + RESUME_DELAY_MS;
      const next = Math.round(e.nativeEvent.contentOffset.x / cardWidth);
      setIndex(Math.max(0, Math.min(SLIDES.length - 1, next)));
    },
    [cardWidth],
  );

  return (
    <View style={styles.wrap}>
      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        decelerationRate="fast"
        snapToInterval={cardWidth}
        snapToAlignment="start"
        onScrollBeginDrag={handleBeginDrag}
        onScrollEndDrag={handleEndDrag}
        onMomentumScrollEnd={handleMomentumEnd}
        style={styles.scroll}
      >
        {SLIDES.map((slide) => {
          const Icon = slide.icon;
          return (
            <Pressable
              key={slide.href}
              onPress={() => router.push(slide.href)}
              style={{ width: cardWidth }}
              accessibilityRole="button"
              accessibilityLabel={`${t(slide.title)} — ${t("common.open")}`}
            >
              <View style={styles.slide}>
                <View style={styles.slideHeader}>
                  <View style={styles.iconBox}>
                    <Icon size={18} color={theme.palette.mint} />
                  </View>
                  <Text style={styles.kicker} numberOfLines={1}>
                    {t("home.aiRecommendations")}
                  </Text>
                </View>

                <Text style={styles.slideTitle}>{t(slide.title)}</Text>
                <Text style={styles.slideDesc} numberOfLines={2}>
                  {t(slide.desc)}
                </Text>

                {facts.length > 0 && (
                  <View style={styles.factRow}>
                    {facts.slice(0, 2).map((fact) => (
                      <Text key={fact} style={styles.fact} numberOfLines={1}>
                        {fact}
                      </Text>
                    ))}
                  </View>
                )}

                <View style={styles.ctaRow}>
                  <Text style={styles.cta}>
                    {t("common.open")} {t(slide.title)}
                  </Text>
                  <ArrowRight size={15} color={theme.palette.mint} />
                </View>
              </View>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.dotsRow}>
        {SLIDES.map((slide, i) => (
          <Pressable
            key={slide.href}
            onPress={() => {
              resumeAt.current = Date.now() + RESUME_DELAY_MS;
              setIndex(i);
            }}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={t(slide.title)}
            style={[styles.dot, i === index && styles.dotActive]}
          />
        ))}
      </View>

      <Text style={styles.hint}>{t("home.aiRecHint")}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: theme.spacing.sm },
  scroll: { flexGrow: 0 },
  slide: {
    backgroundColor: theme.colors.navBackground,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    gap: 6,
    minHeight: 196,
    justifyContent: "space-between",
    ...theme.shadows.fab,
  },
  slideHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  iconBox: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: "rgba(254, 250, 224, 0.14)",
    alignItems: "center",
    justifyContent: "center",
  },
  kicker: {
    flex: 1,
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.2,
    textTransform: "uppercase",
    color: theme.colors.navInactive,
  },
  slideTitle: { fontSize: 21, fontWeight: "800", color: theme.palette.mint, marginTop: 4 },
  slideDesc: { fontSize: 12.5, lineHeight: 18, color: theme.colors.sage },
  factRow: { gap: 2, marginTop: 2 },
  fact: { fontSize: 11, color: "#AEB78A" },
  ctaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 6 },
  cta: { fontSize: 13, fontWeight: "700", color: theme.palette.mint },
  dotsRow: { flexDirection: "row", justifyContent: "center", gap: 6, marginTop: 2 },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: theme.colors.borderStrong,
  },
  dotActive: { width: 20, backgroundColor: theme.colors.primary },
  hint: { fontSize: 11, color: theme.colors.textMuted, textAlign: "center" },
});
