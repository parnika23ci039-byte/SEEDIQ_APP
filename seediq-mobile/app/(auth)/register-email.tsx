import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { Button, Input, OtpInput } from "@/components/ui";
import { AuthHeader, BackLink, FooterLink, FormError, FormSuccess } from "@/components/brand";
import { theme } from "@/theme/theme";

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function RegisterScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { requestRegistrationOtp, verifyRegistrationOtp } = useAuth();

  const [step, setStep] = useState<"form" | "otp">("form");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [otp, setOtp] = useState<string[]>(["", "", "", "", "", ""]);
  const [countdown, setCountdown] = useState(600);
  const [resendCooldown, setResendCooldown] = useState(30);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const hasMinLength = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;
  const rulesPassed = [hasMinLength, hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length;

  useEffect(() => {
    if (step !== "otp") return;
    const timer = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
      setResendCooldown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [step]);

  const handleRequestOtp = async () => {
    setError(null);
    setSuccessMsg(null);
    if (!name.trim()) return setError(t("auth.register.errName"));
    if (!email.trim().includes("@")) return setError(t("auth.register.errEmail"));
    if (rulesPassed < 5) return setError(t("auth.register.errRules"));
    if (!passwordsMatch) return setError(t("auth.register.errMismatch"));

    setLoading(true);
    const result = await requestRegistrationOtp(name, email, password);
    setLoading(false);
    if (result.success) {
      setStep("otp");
      setCountdown(600);
      setResendCooldown(30);
      setSuccessMsg(
        result.message ||
          t("auth.register.successSent", { email: email.trim().toLowerCase() }),
      );
    } else {
      setError(result.error || t("auth.register.errStart"));
    }
  };

  const handleVerifyOtp = async () => {
    setError(null);
    const code = otp.join("");
    if (code.length < 6) return setError(t("auth.register.errOtpIncomplete"));

    setLoading(true);
    const result = await verifyRegistrationOtp(email, code);
    setLoading(false);
    if (result.success) {
      router.replace("/(tabs)/home");
    } else {
      setError(result.error || t("auth.register.errVerify"));
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    const result = await requestRegistrationOtp(name, email, password);
    setLoading(false);
    if (result.success) {
      setCountdown(600);
      setResendCooldown(30);
      setOtp(["", "", "", "", "", ""]);
      setSuccessMsg(t("auth.register.successResent"));
    } else {
      setError(result.error || t("auth.register.errResend"));
    }
  };

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "android" ? undefined : "padding"}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AuthHeader
          title={t(step === "form" ? "auth.register.titleForm" : "auth.register.titleOtp")}
          subtitle={
            step === "form"
              ? t("auth.register.subtitleForm")
              : t("auth.register.subtitleOtp", { email: email.trim().toLowerCase() })
          }
        />

        <FormError message={error || ""} />
        {successMsg && !error ? <FormSuccess message={successMsg} /> : null}

        {step === "form" ? (
          <View style={styles.formWrap}>
            <Input
              label={t("auth.register.nameLabel")}
              placeholder={t("auth.register.namePlaceholder")}
              value={name}
              onChangeText={setName}
              disabled={loading}
            />
            <Input
              label={t("auth.register.emailLabel")}
              placeholder={t("auth.register.emailPlaceholder")}
              keyboardType="email-address"
              autoCapitalize="none"
              value={email}
              onChangeText={setEmail}
              disabled={loading}
            />
            <Input
              label={t("auth.register.passwordLabel")}
              placeholder={t("auth.register.passwordPlaceholder")}
              secure
              value={password}
              onChangeText={setPassword}
              disabled={loading}
            />
            <Input
              label={t("auth.register.confirmLabel")}
              placeholder={t("auth.register.confirmPlaceholder")}
              secure
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              disabled={loading}
            />

            <View style={styles.rulesCard}>
              <Text style={styles.rulesTitle}>{t("auth.register.rulesTitle")}</Text>
              <Text style={[styles.rule, hasMinLength && styles.ruleOk]}>{t("auth.register.ruleLength")}</Text>
              <Text style={[styles.rule, hasUpper && styles.ruleOk]}>{t("auth.register.ruleUpper")}</Text>
              <Text style={[styles.rule, hasLower && styles.ruleOk]}>{t("auth.register.ruleLower")}</Text>
              <Text style={[styles.rule, hasNumber && styles.ruleOk]}>{t("auth.register.ruleNumber")}</Text>
              <Text style={[styles.rule, hasSpecial && styles.ruleOk]}>{t("auth.register.ruleSpecial")}</Text>
              {confirmPassword.length > 0 && (
                <Text style={[styles.rule, passwordsMatch && rulesPassed === 5 ? styles.ruleOk : styles.ruleWarn]}>
                  {t(passwordsMatch ? "auth.register.ruleMatch" : "auth.register.ruleMismatch")}
                </Text>
              )}
              {password.length > 0 && (
                <Text style={styles.strength}>
                  {t("auth.register.strength", {
                    level: t(
                      rulesPassed <= 2
                        ? "auth.register.strengthWeak"
                        : rulesPassed <= 4
                          ? "auth.register.strengthMedium"
                          : "auth.register.strengthStrong",
                    ),
                  })}
                </Text>
              )}
            </View>

            <Button
              label={t("auth.register.sendCode")}
              onPress={handleRequestOtp}
              loading={loading}
            />
          </View>
        ) : (
          <View style={styles.formWrap}>
            <BackLink label={t("auth.register.editDetails")} onPress={() => setStep("form")} />
            <OtpInput value={otp} onChange={setOtp} disabled={loading} />
            <Text style={styles.countdown}>
              {t("auth.register.expiresIn", { time: formatTime(countdown) })}
            </Text>
            <Text
              onPress={handleResend}
              style={[styles.resend, resendCooldown > 0 && styles.resendDisabled]}
            >
              {resendCooldown > 0
                ? t("auth.register.resendIn", { seconds: resendCooldown })
                : t("auth.register.resend")}
            </Text>
            <Button
              label={t("auth.register.verifyCreate")}
              onPress={handleVerifyOtp}
              loading={loading}
            />
          </View>
        )}

        <FooterLink
          prompt={t("auth.register.footerPrompt")}
          action={t("auth.register.footerAction")}
          onPress={() => router.replace("/(auth)/login")}
        />
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: theme.spacing.xl, gap: theme.spacing.lg, paddingBottom: 60 },
  formWrap: { gap: theme.spacing.md },
  rulesCard: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radii.md,
    padding: theme.spacing.md,
    gap: 4,
  },
  rulesTitle: { fontSize: 12, fontWeight: "700", color: theme.colors.text, marginBottom: 2 },
  rule: { fontSize: 12, color: theme.colors.textMuted },
  ruleOk: { color: theme.colors.success },
  ruleWarn: { color: theme.colors.warning },
  strength: { fontSize: 12, fontWeight: "700", color: theme.colors.text, marginTop: 4 },
  countdown: { textAlign: "center", color: theme.colors.textMuted, fontSize: 13 },
  resend: { textAlign: "center", color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  resendDisabled: { color: theme.colors.textMuted },
});
