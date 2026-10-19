import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { Button, Input, OtpInput, PhoneField, SegmentedControl } from "@/components/ui";
import { Info } from "lucide-react-native";
import { AuthHeader, BackLink, FooterLink, FormError, FormSuccess } from "@/components/brand";
import { DEFAULT_DIAL_CODE, prettyPhone, validatePhone } from "@/lib/phone";
import { theme } from "@/theme/theme";

type Mode = "phone" | "email";
type Step = "identify" | "code";

const OTP_LENGTH = 4;
const CODE_TTL_SECONDS = 300;
const RESEND_COOLDOWN_SECONDS = 30;

function formatClock(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Sign-in screen — phone number first.
 *
 * The phone number is the account identifier and a 4-digit code is the only
 * credential. Email + password stays available behind the segmented control
 * because the existing admin and researcher accounts still use it; nothing that
 * worked before was removed.
 */
export default function LoginScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { signIn, loginAsGuest, requestPhoneOtp, verifyPhoneOtp, phoneAuthStatus } = useAuth();

  const [mode, setMode] = useState<Mode>("phone");
  const [step, setStep] = useState<Step>("identify");

  // Phone flow
  const [dial, setDial] = useState(DEFAULT_DIAL_CODE);
  const [national, setNational] = useState("");
  const [sendingTo, setSendingTo] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);
  const [code, setCode] = useState<string[]>(["", "", "", ""]);
  const [countdown, setCountdown] = useState(CODE_TTL_SECONDS);
  const [resendCooldown, setResendCooldown] = useState(RESEND_COOLDOWN_SECONDS);

  // Email flow (unchanged behaviour)
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (step !== "code") return;
    const timer = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
      setResendCooldown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [step]);

  const goHome = () => router.replace("/(tabs)/home");

  // ------------------------------------------------------------ send the code
  const handleSendCode = async () => {
    setError(null);
    setInfo(null);

    const check = validatePhone(national, dial);
    if (!check.valid || !check.e164) {
      setError(t(check.errorKey ?? "phoneAuth.errInvalid"));
      return;
    }

    setLoading(true);
    const result = await requestPhoneOtp(check.e164, "login");
    setLoading(false);

    if (result.success) {
      setSendingTo(check.e164);
      setRequestId(result.requestId);
      setStep("code");
      setCountdown(CODE_TTL_SECONDS);
      setResendCooldown(RESEND_COOLDOWN_SECONDS);
      setCode(["", "", "", ""]);
      setInfo(result.message || t("phoneAuth.sentTo", { phone: prettyPhone(check.e164, dial) }));
      return;
    }

    setError(result.error || t("phoneAuth.errStart"));
  };

  // ---------------------------------------------------------- verify the code
  const handleVerify = async () => {
    setError(null);
    const entered = code.join("");
    if (entered.length !== OTP_LENGTH) {
      setError(t("phoneAuth.errOtpIncomplete"));
      return;
    }
    if (!sendingTo) {
      setStep("identify");
      return;
    }
    setLoading(true);
    const result = await verifyPhoneOtp(sendingTo, entered, undefined, requestId);
    setLoading(false);
    if (result.success) goHome();
    else setError(result.error || t("phoneAuth.errVerify"));
  };

  // --------------------------------------------------------------- email flow
  const handleEmailSignIn = async () => {
    setError(null);
    const trimmed = email.trim();
    if (!trimmed) return setError(t("auth.login.errEmailRequired"));
    if (!trimmed.includes("@")) return setError(t("auth.login.errEmailInvalid"));
    if (!password) return setError(t("auth.login.errPasswordRequired"));
    setLoading(true);
    const result = await signIn(trimmed, password);
    setLoading(false);
    if (result.success) goHome();
    else setError(result.error || t("auth.login.errInvalid"));
  };

  const handleGuest = async () => {
    setError(null);
    setLoading(true);
    const result = await loginAsGuest();
    setLoading(false);
    if (result.success) goHome();
    else setError(result.error || t("auth.login.errGuest"));
  };

  const switchMode = (next: Mode) => {
    setMode(next);
    setStep("identify");
    setError(null);
    setInfo(null);
  };

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "android" ? undefined : "padding"}>
      <ScrollView
        style={styles.fill}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.headerWrap}>
          <AuthHeader title={t("auth.login.title")} subtitle={t("auth.login.subtitle")} />
        </View>

        <SegmentedControl<Mode>
          value={mode}
          onChange={switchMode}
          options={[
            { value: "phone", label: t("phoneAuth.label") },
            { value: "email", label: t("auth.login.emailLabel") },
          ]}
        />

        <FormError message={error || ""} />
        {info && !error ? <FormSuccess message={info} /> : null}

        {mode === "phone" ? (
          step === "identify" ? (
            <View style={styles.formWrap}>
              <PhoneField
                label={t("phoneAuth.label")}
                placeholder={t("phoneAuth.placeholder")}
                value={national}
                onChangeText={setNational}
                dial={dial}
                onDialChange={setDial}
                disabled={loading}
                onSubmitEditing={handleSendCode}
              />
              <Text style={styles.hint}>{t("phoneAuth.subtitle")}</Text>
              <Button label={t("phoneAuth.send")} onPress={handleSendCode} loading={loading} />
              {error ? (
                <Button
                  label={t("phoneAuth.retry")}
                  variant="outline"
                  onPress={handleSendCode}
                  loading={loading}
                />
              ) : null}
              <Button
                label={t("phoneAuth.guest")}
                variant="ghost"
                onPress={handleGuest}
                disabled={loading}
              />
            </View>
          ) : (
            <View style={styles.formWrap}>
              <BackLink label={t("phoneAuth.changeNumber")} onPress={() => setStep("identify")} />
              <Text style={styles.otpTitle}>{t("phoneAuth.otpTitle")}</Text>
              <Text style={styles.otpSubtitle}>
                {t("phoneAuth.otpSubtitle", { phone: prettyPhone(sendingTo, dial) })}
              </Text>
              <OtpInput value={code} onChange={setCode} disabled={loading} length={OTP_LENGTH} />
              <Text style={styles.countdown}>{t("phoneAuth.expiresIn", { time: formatClock(countdown) })}</Text>
              <Pressable onPress={resendCooldown > 0 ? undefined : handleSendCode} disabled={resendCooldown > 0}>
                <Text style={[styles.resend, resendCooldown > 0 && styles.resendDisabled]}>
                  {resendCooldown > 0
                    ? t("phoneAuth.resendIn", { seconds: resendCooldown })
                    : t("phoneAuth.resend")}
                </Text>
              </Pressable>
              <Button label={t("phoneAuth.verify")} onPress={handleVerify} loading={loading} />
              {error ? (
                <Button
                  label={t("phoneAuth.retry")}
                  variant="outline"
                  onPress={handleVerify}
                  loading={loading}
                />
              ) : null}
              <Button
                label={t("phoneAuth.guest")}
                variant="ghost"
                onPress={handleGuest}
                disabled={loading}
              />
            </View>
          )
        ) : (
          <View style={styles.formWrap}>
            <Input
              label={t("auth.login.emailLabel")}
              placeholder={t("auth.login.emailPlaceholder")}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              value={email}
              onChangeText={setEmail}
              disabled={loading}
            />
            <Input
              label={t("auth.login.passwordLabel")}
              placeholder={t("auth.login.passwordPlaceholder")}
              secure
              value={password}
              onChangeText={setPassword}
              disabled={loading}
            />
            <View style={styles.forgotRow}>
              <Text onPress={() => router.push("/(auth)/forgot-password")} style={styles.forgotText}>
                {t("auth.login.forgot")}
              </Text>
            </View>
            <Button label={t("auth.login.submit")} onPress={handleEmailSignIn} loading={loading} />
            <Button
              label={t("auth.login.guest")}
              variant="outline"
              onPress={handleGuest}
              disabled={loading}
            />
            <Text style={styles.hint}>{t("phoneAuth.usePhone")}</Text>
          </View>
        )}

        <FooterLink
          prompt={t("auth.login.footerPrompt")}
          action={t("auth.login.footerAction")}
          onPress={() => router.push("/(auth)/register")}
        />

        {/* Public About access — the SAME screen Profile -> About opens, made
            reachable with no account and no session. The route lives outside
            the (tabs) guard, so nothing authenticated is exposed by it. */}
        <View style={styles.aboutBlock}>
          <Text style={styles.aboutSection}>{t("aboutPublic.section")}</Text>
          <Button
            label={t("aboutPublic.cta")}
            variant="outline"
            icon={<Info size={16} color={theme.colors.primary} />}
            onPress={() => router.push("/about")}
            disabled={loading}
          />
          <Text style={styles.aboutHint}>{t("aboutPublic.hint")}</Text>
        </View>

        {/* Backend capability note — shown only when the probe says SMS is off. */}
        {phoneAuthStatus && !phoneAuthStatus.smsReady ? (
          <Text style={styles.statusNote}>{t("phoneAuth.blockedHint")}</Text>
        ) : null}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: theme.spacing.xl, gap: theme.spacing.lg, flexGrow: 1, justifyContent: "center" },
  headerWrap: { marginBottom: 8 },
  formWrap: { gap: theme.spacing.md },
  hint: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17 },
  forgotRow: { alignItems: "flex-end" },
  forgotText: { color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  otpTitle: { fontSize: 18, fontWeight: "700", color: theme.colors.text },
  otpSubtitle: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 18 },
  countdown: { textAlign: "center", color: theme.colors.textMuted, fontSize: 13 },
  resend: { textAlign: "center", color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  resendDisabled: { color: theme.colors.textMuted },
  statusNote: {
    fontSize: 11,
    color: theme.colors.textMuted,
    lineHeight: 16,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
  },
  aboutBlock: {
    gap: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.lg,
  },
  aboutSection: {
    fontSize: 12,
    fontWeight: "700",
    color: theme.colors.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.6,
    textAlign: "center",
  },
  aboutHint: { fontSize: 11, color: theme.colors.textMuted, textAlign: "center" },
});
