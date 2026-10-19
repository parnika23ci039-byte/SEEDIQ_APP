import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Sprout,
  TrendingUp,
  Activity,
  ShieldCheck,
  Atom,
  ChevronRight,
  Warehouse,
  Images,
  MapPin,
} from "lucide-react-native";
import { Screen, Card, SectionTitle } from "@/components/ui";
import { useI18n, type TranslationKey } from "@/i18n";
import { theme } from "@/theme/theme";

const MODULES: {
  href: "/crop-ai" | "/yield-ai" | "/seed-ai" | "/storage-ai" | "/quantum";
  title: TranslationKey;
  subtitle: TranslationKey;
  desc: TranslationKey;
  icon: typeof Sprout;
}[] = [
  {
    href: "/crop-ai",
    title: "tools.cropTitle",
    subtitle: "tools.cropSubtitle",
    desc: "tools.cropDesc",
    icon: Sprout,
  },
  {
    href: "/yield-ai",
    title: "tools.yieldTitle",
    subtitle: "tools.yieldSubtitle",
    desc: "tools.yieldDesc",
    icon: TrendingUp,
  },
  {
    href: "/seed-ai",
    title: "tools.seedTitle",
    subtitle: "tools.seedSubtitle",
    desc: "tools.seedDesc",
    icon: Activity,
  },
  {
    href: "/storage-ai",
    title: "tools.storageTitle",
    subtitle: "tools.storageSubtitle",
    desc: "tools.storageDesc",
    icon: Warehouse,
  },
  {
    href: "/quantum",
    title: "tools.quantumTitle",
    subtitle: "tools.quantumSubtitle",
    desc: "tools.quantumDesc",
    icon: Atom,
  },
];

// Quantum Labs sits beside the Quantum ML module: one is the prediction stack,
// the other is the interactive circuit the client asked for.
const QUANTUM_LABS = {
  href: "/quantum-labs" as const,
  title: "quantumLabs.title" as const,
  subtitle: "quantumLabs.subtitle" as const,
  desc: "quantumLabs.playgroundHint" as const,
};

export default function ToolsScreen() {
  const router = useRouter();
  const { t } = useI18n();
  return (
    <Screen>
      <SectionTitle>{t("tools.aiModules")}</SectionTitle>
      <Text style={styles.intro}>{t("tools.intro")}</Text>
      <View style={{ gap: theme.spacing.md }}>
        {MODULES.map((m) => {
          const Icon = m.icon;
          return (
            <Pressable key={m.href} onPress={() => router.push(m.href)}>
              <Card style={styles.moduleCard}>
                <View style={styles.moduleTop}>
                  <View style={styles.moduleIconBox}>
                    <Icon size={22} color={theme.colors.primary} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.moduleTitle}>{t(m.title)}</Text>
                    <Text style={styles.moduleSubtitle}>{t(m.subtitle)}</Text>
                  </View>
                  <ChevronRight size={18} color={theme.colors.textMuted} />
                </View>
                <Text style={styles.moduleDesc}>{t(m.desc)}</Text>
              </Card>
            </Pressable>
          );
        })}

        <Pressable onPress={() => router.push(QUANTUM_LABS.href)}>
          <Card style={styles.moduleCard}>
            <View style={styles.moduleTop}>
              <View style={[styles.moduleIconBox, { backgroundColor: theme.colors.featureSoft }]}>
                <Atom size={22} color={theme.colors.pine} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.moduleTitle}>{t(QUANTUM_LABS.title)}</Text>
                <Text style={styles.moduleSubtitle}>{t(QUANTUM_LABS.subtitle)}</Text>
              </View>
              <ChevronRight size={18} color={theme.colors.textMuted} />
            </View>
            <Text style={styles.moduleDesc}>{t(QUANTUM_LABS.desc)}</Text>
          </Card>
        </Pressable>
      </View>

      <SectionTitle>{t("tools.reference")}</SectionTitle>
      <Pressable onPress={() => router.push("/crop-catalog")}>
        <Card style={styles.moduleCard}>
          <View style={styles.moduleTop}>
            <View style={[styles.moduleIconBox, { backgroundColor: theme.colors.primarySoft }]}>
              <Images size={22} color={theme.colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.moduleTitle}>{t("tools.catalogTitle")}</Text>
              <Text style={styles.moduleSubtitle}>{t("tools.catalogSubtitle")}</Text>
            </View>
            <ChevronRight size={18} color={theme.colors.textMuted} />
          </View>
          <Text style={styles.moduleDesc}>{t("tools.catalogDesc")}</Text>
        </Card>
      </Pressable>

      <SectionTitle>{t("tools.statewide")}</SectionTitle>
      <Pressable onPress={() => router.push("/karnataka-map")}>
        <Card style={styles.moduleCard}>
          <View style={styles.moduleTop}>
            <View style={[styles.moduleIconBox, { backgroundColor: theme.colors.primarySoft }]}>
              <MapPin size={22} color={theme.colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.moduleTitle}>{t("map.title")}</Text>
              <Text style={styles.moduleSubtitle}>{t("map.subtitle")}</Text>
            </View>
            <ChevronRight size={18} color={theme.colors.textMuted} />
          </View>
          <Text style={styles.moduleDesc}>{t("map.tapHint")}</Text>
        </Card>
      </Pressable>

      <Pressable onPress={() => router.push("/(tabs)/alerts")}>
        <Card style={styles.moduleCard}>
          <View style={styles.moduleTop}>
            <View style={[styles.moduleIconBox, { backgroundColor: theme.colors.infoSoft }]}>
              <ShieldCheck size={22} color={theme.colors.info} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.moduleTitle}>{t("tools.districtTitle")}</Text>
              <Text style={styles.moduleSubtitle}>{t("tools.districtSubtitle")}</Text>
            </View>
            <ChevronRight size={18} color={theme.colors.textMuted} />
          </View>
          <Text style={styles.moduleDesc}>{t("tools.districtDesc")}</Text>
        </Card>
      </Pressable>
    </Screen>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19, marginTop: -4 },
  moduleCard: { gap: theme.spacing.sm },
  moduleTop: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  moduleIconBox: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: theme.colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  moduleTitle: { fontSize: 16, fontWeight: "700", color: theme.colors.text },
  moduleSubtitle: { fontSize: 12, color: theme.colors.textMuted, marginTop: 1 },
  moduleDesc: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 18 },
});
