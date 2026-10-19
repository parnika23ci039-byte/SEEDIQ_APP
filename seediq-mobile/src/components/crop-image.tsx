import React from "react";
import { Image, ImageStyle, StyleProp, StyleSheet, Text, View, ViewStyle } from "react-native";
import { theme } from "../theme/theme";
import { getCropImageSource, getStorageImageSource } from "../lib/crops";

type Kind = "crop" | "storage";

/**
 * Renders the ORIGINAL SeedIQ crop or storage photo for a crop name.
 * Falls back silently (no placeholder artwork is invented) when the web
 * catalog has no image for that crop.
 */
export function CropImage({
  crop,
  kind = "crop",
  height = 160,
  label,
  style,
}: {
  crop: string;
  kind?: Kind;
  height?: number;
  label?: string;
  style?: StyleProp<ViewStyle>;
}) {
  const source = kind === "crop" ? getCropImageSource(crop) : getStorageImageSource(crop);
  if (!source) return null;

  return (
    <View style={[styles.wrap, { height }, style]}>
      <Image source={source} style={styles.image as StyleProp<ImageStyle>} resizeMode="cover" />
      {label ? (
        <View style={styles.label}>
          <Text style={styles.labelText}>{label}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: theme.radii.lg,
    overflow: "hidden",
    backgroundColor: theme.colors.surfaceMuted,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  image: { width: "100%", height: "100%" },
  label: {
    position: "absolute",
    left: 10,
    bottom: 10,
    backgroundColor: "rgba(40,54,24,0.72)",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: theme.radii.full,
  },
  labelText: { color: "#fff", fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
});
