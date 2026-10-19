import React, { useRef } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
  StyleProp,
  TextStyle,
  ScrollViewProps,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import Slider from "@react-native-community/slider";
import { theme } from "../theme/theme";
import { useI18n, type TranslationKey } from "../i18n";

// ---------------------------------------------------------------------------
// Screen — safe scrollable container with keyboard handling
// ---------------------------------------------------------------------------

interface ScreenProps {
  children: React.ReactNode;
  scroll?: boolean;
  padded?: boolean;
  refreshControl?: ScrollViewProps["refreshControl"];
  style?: StyleProp<ViewStyle>;
}

export function Screen({ children, scroll = true, padded = true, refreshControl, style }: ScreenProps) {
  const content = padded ? <View style={styles.screenPadded}>{children}</View> : children;
  if (!scroll) {
    return (
      <KeyboardAvoidingView
        behavior={Platform.OS === "android" ? undefined : "padding"}
        style={[styles.screenFill, style]}
      >
        {content}
      </KeyboardAvoidingView>
    );
  }
  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "android" ? undefined : "padding"}
      style={[styles.screenFill, style]}
    >
      <ScrollView
        style={styles.flex1}
        contentContainerStyle={padded ? [styles.scrollPadded, styles.scrollGrow] : styles.scrollGrow}
        keyboardShouldPersistTaps="handled"
        refreshControl={refreshControl}
      >
        {content}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

export function Card({
  children,
  style,
  bordered = true,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  bordered?: boolean;
}) {
  return <View style={[styles.card, bordered && styles.cardBordered, style]}>{children}</View>;
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <View style={styles.sectionTitleRow}>
      <Text style={styles.sectionTitle}>{children}</Text>
      {action}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: "primary" | "outline" | "ghost" | "danger";
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}

export function Button({
  label,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
  icon,
  style,
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.buttonBase,
        styles.buttonPadding,
        variant === "primary" && styles.buttonPrimary,
        variant === "outline" && styles.buttonOutline,
        variant === "ghost" && styles.buttonGhost,
        variant === "danger" && styles.buttonDanger,
        pressed && !isDisabled && styles.buttonPressed,
        isDisabled && styles.buttonDisabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator
          size="small"
          color={variant === "primary" || variant === "danger" ? theme.colors.textInverse : theme.colors.primary}
        />
      ) : (
        <>
          {icon}
          <Text
            style={[
              styles.buttonLabel,
              (variant === "primary" || variant === "danger") && styles.buttonLabelPrimary,
              variant === "outline" && styles.buttonLabelOutline,
              variant === "ghost" && styles.buttonLabelGhost,
            ]}
          >
            {label}
          </Text>
        </>
      )}
    </Pressable>
  );
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

interface InputProps extends TextInputProps {
  label?: string;
  error?: string | null;
  secure?: boolean;
  disabled?: boolean;
  suffixToggle?: React.ReactNode;
}

export function Input({ label, error, secure, disabled, suffixToggle, style, ...rest }: InputProps) {
  const { t } = useI18n();
  const [show, setShow] = React.useState(!secure);
  return (
    <View style={styles.inputWrap}>
      {label ? <Text style={styles.inputLabel}>{label}</Text> : null}
      <View style={[styles.inputRow, error && styles.inputRowError]}>
        <TextInput
          style={[styles.inputText, style]}
          secureTextEntry={secure ? !show : false}
          placeholderTextColor={theme.colors.textMuted}
          editable={!disabled}
          {...rest}
        />
        {secure ? (
          <Pressable onPress={() => setShow((s) => !s)} hitSlop={12} style={styles.inputSuffix}>
            <Text style={styles.inputSuffixText}>
              {show ? t("common.hide") : t("common.show")}
            </Text>
          </Pressable>
        ) : suffixToggle ? (
          <View style={styles.inputSuffix}>{suffixToggle}</View>
        ) : null}
      </View>
      {error ? <Text style={styles.inputError}>{error}</Text> : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// SliderField — labeled slider with live value and optimal-range hint
// ---------------------------------------------------------------------------

interface SliderFieldProps {
  label: string;
  value: number;
  onValueChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  hint?: string;
  optimal?: [number, number];
}

export function SliderField({
  label,
  value,
  onValueChange,
  min,
  max,
  step = 1,
  unit = "",
  hint,
  optimal,
}: SliderFieldProps) {
  const { t } = useI18n();
  const statusKey = optimal ? feedbackKey(value, optimal) : null;
  return (
    <View style={styles.sliderWrap}>
      <View style={styles.sliderHeader}>
        <Text style={styles.inputLabel}>{label}</Text>
        <View style={styles.sliderValueRow}>
          {statusKey && (
            <Badge
              label={t(statusKey)}
              tone={statusKey === "common.statusOptimal" ? "success" : "warning"}
              small
            />
          )}
          <Text style={styles.sliderValue}>
            {formatNumber(value)}
            <Text style={styles.sliderUnit}> {unit}</Text>
          </Text>
        </View>
      </View>
      <Slider
        value={value}
        minimumValue={min}
        maximumValue={max}
        step={step}
        onValueChange={onValueChange}
      />
      <View style={styles.sliderFooter}>
        {hint ? <Text style={styles.sliderHint}>{hint}</Text> : <View />}
        {optimal && (
          <Text style={styles.sliderRange}>
            {t("common.ideal", { min: optimal[0], max: optimal[1] })}
          </Text>
        )}
      </View>
    </View>
  );
}

function feedbackKey(val: number, [optMin, optMax]: [number, number]): TranslationKey {
  if (val < optMin) return "common.statusLow";
  if (val > optMax) return "common.statusHigh";
  return "common.statusOptimal";
}

function formatNumber(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

// ---------------------------------------------------------------------------
// PickerField — labeled select input
// ---------------------------------------------------------------------------

interface PickerFieldProps {
  label: string;
  value: string;
  onValueChange: (v: string) => void;
  items: string[];
  hint?: string;
}

export function PickerField({ label, value, onValueChange, items, hint }: PickerFieldProps) {
  return (
    <View style={styles.inputWrap}>
      {label ? <Text style={styles.inputLabel}>{label}</Text> : null}
      <View style={styles.pickerRow}>
        <Picker
          selectedValue={value}
          onValueChange={(itemValue) => onValueChange(String(itemValue))}
          style={styles.picker}
          dropdownIconColor={theme.colors.textSecondary}
        >
          {items.map((item) => (
            <Picker.Item key={item} label={item} value={item} />
          ))}
        </Picker>
      </View>
      {hint ? <Text style={styles.sliderHint}>{hint}</Text> : null}
    </View>
  );
}

import { Picker } from "@react-native-picker/picker";
import { DIAL_CODES } from "../lib/phone";

// ---------------------------------------------------------------------------
// Row — label/value pair
// ---------------------------------------------------------------------------

export function Row({
  label,
  value,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "info";
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={[styles.rowValue, tone && toneStyle(tone)]}>{value}</Text>
    </View>
  );
}

function toneStyle(tone: NonNullable<RowProps["tone"]>): TextStyle {
  switch (tone) {
    case "success":
      return { color: theme.colors.success };
    case "warning":
      return { color: theme.colors.warning };
    case "danger":
      return { color: theme.colors.danger };
    case "info":
      return { color: theme.colors.info };
    default:
      return {};
  }
}

interface RowProps {
  tone?: "default" | "success" | "warning" | "danger" | "info";
}

// ---------------------------------------------------------------------------
// Stat — big number metric
// ---------------------------------------------------------------------------

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  sub?: string;
}) {
  return (
    <Card style={styles.statCard}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
      {sub ? <Text style={styles.statSub}>{sub}</Text> : null}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Badge
// ---------------------------------------------------------------------------

export function Badge({
  label,
  tone = "neutral",
  small = false,
}: {
  label: string;
  tone?: "neutral" | "success" | "warning" | "danger" | "info" | "primary";
  small?: boolean;
}) {
  return (
    <View
      style={[
        styles.badge,
        small && styles.badgeSmall,
        tone === "success" && styles.badgeSuccess,
        tone === "warning" && styles.badgeWarning,
        tone === "danger" && styles.badgeDanger,
        tone === "info" && styles.badgeInfo,
        tone === "primary" && styles.badgePrimary,
      ]}
    >
      <Text
        style={[
          styles.badgeText,
          small && styles.badgeTextSmall,
          tone === "success" && styles.badgeTextSuccess,
          tone === "warning" && styles.badgeTextWarning,
          tone === "danger" && styles.badgeTextDanger,
          tone === "info" && styles.badgeTextInfo,
          tone === "primary" && styles.badgeTextPrimary,
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  message?: string;
  action?: React.ReactNode;
}) {
  return (
    <View style={styles.emptyWrap}>
      {icon}
      <Text style={styles.emptyTitle}>{title}</Text>
      {message ? <Text style={styles.emptyMessage}>{message}</Text> : null}
      {action}
    </View>
  );
}

// ---------------------------------------------------------------------------
// ErrorBanner + retry
// ---------------------------------------------------------------------------

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n();
  return (
    <View style={styles.errorBanner}>
      <View style={styles.flex1}>
        <Text style={styles.errorTitle}>{t("common.somethingWentWrong")}</Text>
        <Text style={styles.errorMessage}>{message}</Text>
      </View>
      {onRetry && (
        <Pressable onPress={onRetry} hitSlop={8} style={styles.retryButton}>
          <Text style={styles.retryText}>{t("common.retry")}</Text>
        </Pressable>
      )}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

export function Loading({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <View style={styles.loadingWrap}>
      <ActivityIndicator size="large" color={theme.colors.primary} />
      <Text style={styles.loadingText}>{label ?? t("common.loading")}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// ProgressBar
// ---------------------------------------------------------------------------

export function ProgressBar({ value, tone = "primary" }: { value: number; tone?: "primary" | "warning" | "danger" | "info" | "success" }) {
  const pct = Math.max(0, Math.min(100, value));
  const barColor =
    tone === "danger"
      ? theme.colors.danger
      : tone === "warning"
        ? theme.colors.warning
        : tone === "info"
          ? theme.colors.info
          : theme.colors.primary;
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width: `${pct}%`, backgroundColor: barColor }]} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// OtpInput — segmented code entry (length-configurable)
//
// Phone verification uses a 4-digit code, so the box count is a parameter; the
// previous 6-digit layout was hard-wired. A pasted code of any length fills the
// boxes from the left and focuses the next empty one.
// ---------------------------------------------------------------------------

export function OtpInput({
  value,
  onChange,
  disabled,
  length = 6,
}: {
  value: string[];
  onChange: (digits: string[]) => void;
  disabled?: boolean;
  length?: number;
}) {
  const refs = useRef<(TextInput | null)[]>([]);

  const setDigit = (index: number, text: string) => {
    const digits = text.replace(/\D/g, "");
    if (digits.length > 1) {
      // Pasted full code
      const next = [...value];
      for (let i = 0; i < length; i++) next[i] = digits[i] || "";
      onChange(next);
      refs.current[Math.min(digits.length, length - 1)]?.focus();
      return;
    }
    const next = [...value];
    next[index] = digits;
    onChange(next);
    if (digits && index < length - 1) refs.current[index + 1]?.focus();
  };

  return (
    <View style={styles.otpRow}>
      {value.map((digit, i) => (
        <TextInput
          key={i}
          ref={(el) => {
            refs.current[i] = el;
          }}
          style={[styles.otpBox, length <= 4 && styles.otpBoxWide, digit ? styles.otpBoxFilled : null]}
          value={digit}
          editable={!disabled}
          keyboardType="number-pad"
          textContentType="oneTimeCode"
          autoComplete="sms-otp"
          maxLength={1}
          onChangeText={(t) => setDigit(i, t)}
          onKeyPress={({ nativeEvent }) => {
            if (nativeEvent.key === "Backspace" && !value[i] && i > 0) {
              refs.current[i - 1]?.focus();
            }
          }}
        />
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------
// PhoneField — country dial code + national number, the primary login input
// ---------------------------------------------------------------------------

interface PhoneFieldProps {
  label: string;
  placeholder?: string;
  value: string;
  onChangeText: (v: string) => void;
  dial: string;
  onDialChange: (dial: string) => void;
  disabled?: boolean;
  error?: string | null;
  /** Called when the user presses the keyboard's submit key. */
  onSubmitEditing?: () => void;
}

export function PhoneField({
  label,
  placeholder,
  value,
  onChangeText,
  dial,
  onDialChange,
  disabled,
  error,
  onSubmitEditing,
}: PhoneFieldProps) {
  return (
    <View style={styles.inputWrap}>
      <Text style={styles.inputLabel}>{label}</Text>
      <View style={[styles.phoneRow, error && styles.inputRowError]}>
        <View style={styles.dialBox}>
          <Picker
            selectedValue={dial}
            onValueChange={(v) => onDialChange(String(v))}
            enabled={!disabled}
            style={styles.dialPicker}
            dropdownIconColor={theme.colors.textSecondary}
          >
            {DIAL_CODES.map((c) => (
              <Picker.Item key={c.dial} label={c.dial} value={c.dial} />
            ))}
          </Picker>
        </View>
        <TextInput
          style={styles.phoneInput}
          value={value}
          onChangeText={(t) => onChangeText(t.replace(/[^\d\s]/g, ""))}
          placeholder={placeholder}
          placeholderTextColor={theme.colors.textMuted}
          keyboardType="phone-pad"
          inputMode="tel"
          maxLength={14}
          editable={!disabled}
          returnKeyType="done"
          onSubmitEditing={onSubmitEditing}
        />
      </View>
      {error ? <Text style={styles.inputError}>{error}</Text> : null}
    </View>
  );
}

// ---------------------------------------------------------------------------
// SegmentedControl — small inline tab strip
// ---------------------------------------------------------------------------

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            style={[styles.segment, active && styles.segmentActive]}
          >
            <Text style={[styles.segmentLabel, active && styles.segmentLabelActive]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  flex1: { flex: 1 },
  screenFill: { flex: 1, backgroundColor: theme.colors.background },
  screenPadded: { padding: theme.spacing.lg, gap: theme.spacing.md },
  scrollPadded: { padding: theme.spacing.lg, gap: theme.spacing.md, paddingBottom: theme.spacing.xxl + 20 },
  scrollGrow: { flexGrow: 1 },

  card: {
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.lg,
    gap: theme.spacing.sm,
    ...theme.shadows.card,
  },
  cardBordered: { borderWidth: 1, borderColor: theme.colors.border },

  sectionTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: theme.spacing.sm,
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: "700",
    color: theme.colors.text,
  },

  buttonBase: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: theme.spacing.sm,
    borderRadius: theme.radii.md,
    minHeight: 50,
  },
  buttonPadding: { paddingHorizontal: theme.spacing.lg },
  buttonPrimary: { backgroundColor: theme.colors.primary },
  buttonOutline: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.primaryBorder,
  },
  buttonGhost: { backgroundColor: "transparent" },
  buttonDanger: { backgroundColor: theme.colors.danger },
  buttonPressed: { opacity: 0.85 },
  buttonDisabled: { opacity: 0.5 },
  buttonLabel: { fontSize: 15, fontWeight: "700", color: theme.colors.primary },
  buttonLabelPrimary: { color: theme.colors.textInverse },
  buttonLabelOutline: { color: theme.colors.primary },
  buttonLabelGhost: { color: theme.colors.textSecondary },

  inputWrap: { gap: 6 },
  inputLabel: { fontSize: 13, fontWeight: "600", color: theme.colors.text },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    minHeight: 50,
    paddingHorizontal: theme.spacing.md,
  },
  inputRowError: { borderColor: theme.colors.danger },
  inputText: { flex: 1, fontSize: 15, color: theme.colors.text, paddingVertical: 12 },
  inputSuffix: { paddingHorizontal: 4 },
  inputSuffixText: { color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  inputError: { color: theme.colors.danger, fontSize: 12 },

  sliderWrap: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.lg,
    padding: theme.spacing.md,
    gap: 4,
  },
  sliderHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sliderValueRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  sliderValue: { fontSize: 16, fontWeight: "700", color: theme.colors.primaryDark },
  sliderUnit: { fontSize: 11, fontWeight: "500", color: theme.colors.textMuted },
  sliderFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sliderHint: { fontSize: 11, color: theme.colors.textMuted, flex: 1, flexWrap: "wrap" },
  sliderRange: { fontSize: 11, color: theme.colors.textMuted },

  pickerRow: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    overflow: "hidden",
  },
  picker: { height: 50, width: "100%", color: theme.colors.text },

  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    gap: theme.spacing.md,
  },
  rowLabel: { fontSize: 13, color: theme.colors.textSecondary, flexShrink: 1 },
  rowValue: { fontSize: 13, fontWeight: "600", color: theme.colors.text, textAlign: "right" },

  statCard: { flex: 1, padding: theme.spacing.md, gap: 2 },
  statLabel: { fontSize: 11, fontWeight: "600", color: theme.colors.textMuted, textTransform: "uppercase", letterSpacing: 0.5 },
  statValue: { fontSize: 22, fontWeight: "700", color: theme.colors.text },
  statSub: { fontSize: 11, color: theme.colors.textMuted },

  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: theme.radii.full,
    backgroundColor: theme.colors.surfaceMuted,
  },
  badgeSmall: { paddingHorizontal: 7, paddingVertical: 2 },
  badgeSuccess: { backgroundColor: theme.colors.successSoft },
  badgeWarning: { backgroundColor: theme.colors.warningSoft },
  badgeDanger: { backgroundColor: theme.colors.dangerSoft },
  badgeInfo: { backgroundColor: theme.colors.infoSoft },
  badgePrimary: { backgroundColor: theme.colors.primarySoft },
  badgeText: { fontSize: 12, fontWeight: "600", color: theme.colors.textSecondary },
  badgeTextSmall: { fontSize: 10 },
  badgeTextSuccess: { color: theme.colors.success },
  badgeTextWarning: { color: theme.colors.warning },
  badgeTextDanger: { color: theme.colors.danger },
  badgeTextInfo: { color: theme.colors.info },
  badgeTextPrimary: { color: theme.colors.primary },

  emptyWrap: {
    alignItems: "center",
    justifyContent: "center",
    padding: theme.spacing.xxl,
    gap: theme.spacing.sm,
  },
  emptyTitle: { fontSize: 16, fontWeight: "600", color: theme.colors.text },
  emptyMessage: { fontSize: 13, color: theme.colors.textMuted, textAlign: "center", lineHeight: 19 },

  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.dangerSoft,
    borderColor: theme.colors.dangerSoft,
    borderWidth: 1,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    gap: theme.spacing.md,
  },
  errorTitle: { color: theme.colors.danger, fontWeight: "700", fontSize: 13 },
  errorMessage: { color: theme.colors.danger, fontSize: 13, marginTop: 2 },
  retryButton: {
    backgroundColor: theme.colors.danger,
    borderRadius: theme.radii.sm,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  retryText: { color: theme.colors.textInverse, fontWeight: "700", fontSize: 12 },

  loadingWrap: {
    alignItems: "center",
    justifyContent: "center",
    padding: theme.spacing.xxl,
    gap: theme.spacing.md,
  },
  loadingText: { color: theme.colors.textMuted, fontSize: 13 },

  progressTrack: {
    height: 8,
    borderRadius: theme.radii.full,
    backgroundColor: theme.colors.surfaceMuted,
    overflow: "hidden",
  },
  progressFill: { height: "100%", borderRadius: theme.radii.full },

  otpRow: { flexDirection: "row", justifyContent: "center", gap: 10 },
  otpBox: {
    width: 46,
    height: 56,
    borderWidth: 1.5,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    textAlign: "center",
    fontSize: 22,
    fontWeight: "700",
    color: theme.colors.text,
    backgroundColor: theme.colors.surface,
  },
  otpBoxFilled: { borderColor: theme.colors.primary },
  otpBoxWide: { width: 58 },

  phoneRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radii.md,
    minHeight: 50,
    paddingRight: theme.spacing.md,
  },
  dialBox: {
    width: 92,
    borderRightWidth: 1,
    borderRightColor: theme.colors.border,
    justifyContent: "center",
  },
  dialPicker: { height: 48, width: "100%", color: theme.colors.text },
  phoneInput: {
    flex: 1,
    fontSize: 17,
    letterSpacing: 0.5,
    color: theme.colors.text,
    paddingVertical: 12,
    paddingHorizontal: theme.spacing.md,
  },

  segmented: {
    flexDirection: "row",
    backgroundColor: theme.colors.surfaceMuted,
    borderRadius: theme.radii.full,
    padding: 4,
    gap: 4,
  },
  segment: {
    flex: 1,
    paddingVertical: 9,
    borderRadius: theme.radii.full,
    alignItems: "center",
  },
  segmentActive: { backgroundColor: theme.colors.primary },
  segmentLabel: { fontSize: 13, fontWeight: "700", color: theme.colors.textSecondary },
  segmentLabelActive: { color: theme.colors.textInverse },
});
