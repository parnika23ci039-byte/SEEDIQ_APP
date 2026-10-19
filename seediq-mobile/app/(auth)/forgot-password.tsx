import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { Button, Input, OtpInput } from "@/components/ui";
import { AuthHeader, BackLink, FooterLink, FormError, FormSuccess } from "@/components/brand";
import { theme } from "@/theme/theme";

type Step = "email" | "otp" | "new_password" | "success";

function formatTime(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { requestPasswordResetOtp, verifyPasswordResetOtp, resetPassword } = useAuth();

  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState<string[]>(["", "", "", "", "", ""]);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [countdown, setCountdown] = useState(600);
  const [resendCooldown, setResendCooldown] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const hasMinLength = newPassword.length >= 8;
  const hasUpper = /[A-Z]/.test(newPassword);
  const hasLower = /[a-z]/.test(newPassword);
  const hasNumber = /[0-9]/.test(newPassword);
  const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(newPassword);
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;
  const rulesPassed = [hasMinLength, hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length;

  useEffect(() => {
    if (step !== "otp") return;
    const timer = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
      setResendCooldown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [step]);

  const titles: Record<Step, string> = {
    email: t("auth.forgot.titleEmail"),
    otp: t("auth.forgot.titleOtp"),
    new_password: t("auth.forgot.titleNew"),
    success: t("auth.forgot.titleSuccess"),
  };
  const subtitles: Record<Step, string> = {
    email: t("auth.forgot.subtitleEmail"),
    otp: t("auth.forgot.subtitleOtp", { email: email.trim().toLowerCase() }),
    new_password: t("auth.forgot.subtitleNew"),
    success: t("auth.forgot.subtitleSuccess"),
  };

  const handleRequestOtp = async () => {
    setError(null);
    if (!email.trim().includes("@")) return setError(t("auth.forgot.errEmail"));
    setLoading(true);
    const result = await requestPasswordResetOtp(email);
    setLoading(false);
    if (result.success) {
      setStep("otp");
      setCountdown(600);
      setResendCooldown(30);
      setSuccessMsg(result.message || t("auth.forgot.successCodeSent"));
    } else {
      setError(result.error || t("auth.forgot.errSend"));
    }
  };

  const handleVerifyOtp = async () => {
    setError(null);
    const code = otp.join("");
    if (code.length < 6) return setError(t("auth.forgot.errOtpIncomplete"));
    setLoading(true);
    const result = await verifyPasswordResetOtp(email, code);
    setLoading(false);
    if (result.success) {
      setStep("new_password");
      setSuccessMsg(t("auth.forgot.successVerified"));
    } else {
      setError(result.error || t("auth.forgot.errVerify"));
    }
  };

  const handleResend = async () => {
    if (resendCooldown > 0) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    const result = await requestPasswordResetOtp(email);
    setLoading(false);
    if (result.success) {
      setCountdown(600);
      setResendCooldown(30);
      setOtp(["", "", "", "", "", ""]);
      setSuccessMsg(t("auth.forgot.successResent"));
    } else {
      setError(result.error || t("auth.forgot.errResend"));
    }
  };

  const handleResetPassword = async () => {
    setError(null);
    if (rulesPassed < 5) return setError(t("auth.forgot.errRules"));
    if (!passwordsMatch) return setError(t("auth.forgot.errMismatch"));
    setLoading(true);
    const result = await resetPassword(email, otp.join(""), newPassword);
    setLoading(false);
    if (result.success) {
      setStep("success");
      setSuccessMsg(null);
    } else {
      setError(result.error || t("auth.forgot.errUpdate"));
    }
  };

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "android" ? undefined : "padding"}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AuthHeader title={titles[step]} subtitle={subtitles[step]} />

        <FormError message={error || ""} />
        {successMsg && !error ? <FormSuccess message={successMsg} /> : null}

        {step === "email" && (
          <View style={styles.formWrap}>
            <Input
              label={t("auth.forgot.emailLabel")}
              placeholder={t("auth.forgot.emailPlaceholder")}
              keyboardType="email-address"
              autoCapitalize="none"
              value={email}
              onChangeText={setEmail}
              disabled={loading}
            />
            <Button
              label={t("auth.forgot.sendCode")}
              onPress={handleRequestOtp}
              loading={loading}
            />
          </View>
        )}

        {step === "otp" && (
          <View style={styles.formWrap}>
            <BackLink label={t("auth.forgot.changeEmail")} onPress={() => setStep("email")} />
            <OtpInput value={otp} onChange={setOtp} disabled={loading} />
            <Text style={styles.countdown}>
              {t("auth.forgot.expiresIn", { time: formatTime(countdown) })}
            </Text>
            <Text onPress={handleResend} style={[styles.resend, resendCooldown > 0 && styles.resendDisabled]}>
              {resendCooldown > 0
                ? t("auth.forgot.resendIn", { seconds: resendCooldown })
                : t("auth.forgot.resend")}
            </Text>
            <Button label={t("auth.forgot.verifyCode")} onPress={handleVerifyOtp} loading={loading} />
          </View>
        )}

        {step === "new_password" && (
          <View style={styles.formWrap}>
            <Input
              label={t("auth.forgot.newPasswordLabel")}
              placeholder={t("auth.forgot.newPasswordPlaceholder")}
              secure
              value={newPassword}
              onChangeText={setNewPassword}
              disabled={loading}
            />
            <Input
              label={t("auth.forgot.confirmLabel")}
              placeholder={t("auth.forgot.confirmPlaceholder")}
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
            </View>
            <Button
              label={t("auth.forgot.updatePassword")}
              onPress={handleResetPassword}
              loading={loading}
            />
          </View>
        )}

        {step === "success" && (
          <View style={styles.formWrap}>
            <Button
              label={t("auth.forgot.continueToSignIn")}
              onPress={() => router.replace("/(auth)/login")}
            />
          </View>
        )}

        {step !== "success" && (
          <FooterLink
            prompt={t("auth.forgot.footerPrompt")}
            action={t("auth.forgot.footerAction")}
            onPress={() => router.replace("/(auth)/login")}
          />
        )}
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
  countdown: { textAlign: "center", color: theme.colors.textMuted, fontSize: 13 },
  resend: { textAlign: "center", color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  resendDisabled: { color: theme.colors.textMuted },
});
