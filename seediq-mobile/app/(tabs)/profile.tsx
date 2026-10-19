import React, { useState } from "react";
import { Alert, Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import {
  LogOut,
  ShieldCheck,
  Activity as ActivityIcon,
  Server,
  ChevronRight,
  Info,
  Languages,
  Check,
} from "lucide-react-native";
import { Screen, Card, Row, Badge, Button, SectionTitle, Loading } from "@/components/ui";
import { BrandLogo } from "@/components/brand";
import { useAuth } from "@/lib/auth-context";
import { useI18n, type LanguageCode } from "@/i18n";
import { api } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import { theme } from "@/theme/theme";

export default function ProfileScreen() {
  const router = useRouter();
  const { t, language, setLanguage, languages } = useI18n();
  const { user, logout } = useAuth();
  const [health, setHealth] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const checkHealth = async () => {
    setChecking(true);
    try {
      const res = await api<{ status: string; version?: string }>("/api/health", { timeoutMs: 8000 });
      setHealth(`${res.status}${res.version ? ` · v${res.version}` : ""}`);
    } catch {
      setHealth(t("common.unreachable"));
    } finally {
      setChecking(false);
    }
  };

  const handleLanguage = (code: LanguageCode) => {
    if (code === language) return;
    // Switches instantly: the whole tree re-renders, no restart and no logout.
    void setLanguage(code);
  };

  const handleLogout = () => {
    Alert.alert(t("profile.signOutTitle"), t("profile.signOutMessage"), [
      { text: t("common.cancel"), style: "cancel" },
      {
        text: t("profile.signOut"),
        style: "destructive",
        onPress: async () => {
          await logout();
          router.replace("/(auth)/login");
        },
      },
    ]);
  };

  return (
    <Screen>
      <SectionTitle>{t("profile.title")}</SectionTitle>

      <Card>
        <View style={styles.profileRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {(user?.name || user?.username || "U").charAt(0).toUpperCase()}
            </Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={styles.name} numberOfLines={1}>
              {user?.display_name || user?.name || user?.username}
            </Text>
            <Text style={styles.email} numberOfLines={1}>
              {user?.email}
            </Text>
          </View>
        </View>
        <Row label={t("profile.role")} value={user?.role ?? "—"} />
        <Row label={t("profile.provider")} value={user?.provider ?? "—"} />
        {user?.isGuest && (
          <Row label={t("profile.session")} value={t("session.guestSessionValue")} tone="warning" />
        )}
      </Card>

      {/* Language — applies to the whole app immediately, persisted locally. */}
      <SectionTitle>{t("language.sectionTitle")}</SectionTitle>
      <Card>
        <View style={styles.langHeader}>
          <Languages size={16} color={theme.colors.primary} />
          <Text style={styles.langLabel}>{t("language.label")}</Text>
        </View>
        {languages.map((option) => {
          const active = option.code === language;
          return (
            <Pressable
              key={option.code}
              onPress={() => handleLanguage(option.code)}
              style={[styles.langRow, active && styles.langRowActive]}
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
            >
              <Text style={[styles.langOption, active && styles.langOptionActive]}>
                {option.label}
              </Text>
              {active ? <Check size={17} color={theme.colors.primary} /> : null}
            </Pressable>
          );
        })}
        <Text style={styles.langHint}>{t("language.hint")}</Text>
      </Card>

      <SectionTitle>{t("profile.server")}</SectionTitle>
      <Card>
        <Row label={t("profile.apiEndpoint")} value={API_BASE_URL} />
        <Row
          label={t("profile.status")}
          value={
            checking ? (
              t("common.checking")
            ) : health ? (
              <Badge
                label={health}
                tone={health === t("common.unreachable") ? "danger" : "success"}
                small
              />
            ) : (
              t("common.notChecked")
            )
          }
        />
        <Button
          label={t("profile.checkHealth")}
          variant="outline"
          onPress={checkHealth}
          loading={checking}
          style={{ marginTop: 8 }}
        />
      </Card>

      {(user?.role === "Admin" || user?.role === "Researcher") && (
        <>
          <SectionTitle>{t("profile.administration")}</SectionTitle>
          <Card>
            <PressableRow
              icon={<ShieldCheck size={18} color={theme.colors.primary} />}
              title={t("profile.adminConsole")}
              subtitle={t("profile.adminConsoleSubtitle")}
              onPress={() => router.push("/(tabs)/admin")}
            />
          </Card>
        </>
      )}

      <SectionTitle>{t("profile.about")}</SectionTitle>
      <Card>
        <View style={styles.aboutRow}>
          <Info size={15} color={theme.colors.textMuted} />
          <Text style={styles.aboutText}>{t("profile.aboutText")}</Text>
        </View>
        <PressableRow
          icon={<BrandLogo width={26} radius={7} />}
          title={t("profile.aboutSeedIq")}
          subtitle={t("profile.aboutSeedIqSubtitle")}
          onPress={() => router.push("/about")}
        />
      </Card>

      <Button
        label={t("profile.signOut")}
        variant="danger"
        icon={<LogOut size={16} color="#fff" />}
        onPress={handleLogout}
      />
    </Screen>
  );
}

function PressableRow({
  icon,
  title,
  subtitle,
  onPress,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  // The whole row is the touch target. Attaching `onPress` to the chevron
  // alone made the row look tappable but only respond on an 18px icon
  // (Profile -> About and Profile -> Admin console both appeared dead).
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.pressableRow, pressed && styles.pressableRowPressed]}
    >
      {icon}
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowSubtitle}>{subtitle}</Text>
      </View>
      <ChevronRight size={18} color={theme.colors.textMuted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  profileRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md, marginBottom: 8 },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: theme.colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: theme.colors.primaryBorder,
  },
  avatarText: { fontSize: 22, fontWeight: "800", color: theme.colors.primary },
  name: { fontSize: 17, fontWeight: "700", color: theme.colors.text },
  email: { fontSize: 13, color: theme.colors.textMuted, marginTop: 2 },
  pressableRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 8 },
  pressableRowPressed: { opacity: 0.65 },
  rowTitle: { fontSize: 14, fontWeight: "600", color: theme.colors.text },
  rowSubtitle: { fontSize: 12, color: theme.colors.textMuted, marginTop: 1 },
  aboutRow: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  aboutText: { flex: 1, fontSize: 12, color: theme.colors.textMuted, lineHeight: 18 },
  langHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 4 },
  langLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.text },
  langRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
  },
  langRowActive: {
    borderColor: theme.colors.primaryBorder,
    backgroundColor: theme.colors.primarySoft,
  },
  langOption: { fontSize: 15, fontWeight: "600", color: theme.colors.text },
  langOptionActive: { color: theme.colors.primary },
  langHint: { fontSize: 11, color: theme.colors.textMuted, marginTop: 4, lineHeight: 16 },
});
