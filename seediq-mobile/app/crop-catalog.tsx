import React, { useMemo, useState } from "react";
import { FlatList, StyleSheet, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Search } from "lucide-react-native";
import { theme } from "@/theme/theme";
import { useI18n } from "@/i18n";
import { CROP_VARIETIES, getCropAsset } from "@/lib/crops";
import { CropImage } from "@/components/crop-image";

/**
 * Mirrors the web Storage AI "master catalog" grid: the full SeedIQ crop list
 * (CROP_VARIETIES) rendered with the ORIGINAL crop + storage photos and a
 * client-side search filter. No crop data is invented — names and imagery come
 * from the same source the web app uses.
 */
export default function CropCatalogScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const [query, setQuery] = useState("");

  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CROP_VARIETIES.filter((c) => !q || c.toLowerCase().includes(q));
  }, [query]);

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <View style={styles.backBox}>
          <ChevronLeft
            size={22}
            color={theme.colors.text}
            onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/tools"))}
            hitSlop={12}
          />
          <Text
            style={styles.backText}
            onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)/tools"))}
          >
            {t("common.back")}
          </Text>
        </View>
        <Text style={styles.title}>{t("catalog.title")}</Text>
        <Text style={styles.subtitle}>
          {t("catalog.subtitle", { count: CROP_VARIETIES.length })}
        </Text>
        <View style={styles.searchRow}>
          <Search size={16} color={theme.colors.textMuted} />
          <TextInput
            style={styles.searchInput}
            value={query}
            onChangeText={setQuery}
            placeholder={t("catalog.searchPlaceholder")}
            placeholderTextColor={theme.colors.textMuted}
            autoCorrect={false}
          />
        </View>
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => item}
        contentContainerStyle={styles.listContent}
        numColumns={2}
        columnWrapperStyle={styles.column}
        renderItem={({ item }) => {
          const asset = getCropAsset(item);
          return (
            <View style={styles.cell}>
              <CropImage crop={item} kind="crop" height={104} label={item} />
              {asset?.storageImageSource ? <CropImage crop={item} kind="storage" height={72} /> : null}
            </View>
          );
        }}
        ListEmptyComponent={
          <Text style={styles.empty}>{t("catalog.empty", { query })}</Text>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.colors.background },
  header: { padding: theme.spacing.lg, gap: 6 },
  backBox: { flexDirection: "row", alignItems: "center", gap: 2 },
  backText: { fontSize: 14, color: theme.colors.text, fontWeight: "600" },
  title: { fontSize: 22, fontWeight: "800", color: theme.colors.text, marginTop: theme.spacing.sm },
  subtitle: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 19 },
  searchRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    paddingHorizontal: theme.spacing.md,
    marginTop: theme.spacing.sm,
  },
  searchInput: { flex: 1, fontSize: 15, color: theme.colors.text, paddingVertical: 12 },
  listContent: { paddingHorizontal: theme.spacing.lg, paddingBottom: theme.spacing.xxl, gap: theme.spacing.sm },
  column: { gap: theme.spacing.sm },
  cell: { flex: 1, gap: 4, marginBottom: theme.spacing.sm },
  empty: { textAlign: "center", color: theme.colors.textMuted, marginTop: theme.spacing.xl },
});
