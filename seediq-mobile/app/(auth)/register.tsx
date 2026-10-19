import React, { useEffect, useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "@/lib/auth-context";
import { useI18n } from "@/i18n";
import { Info } from "lucide-react-native";
import { Button, Input, OtpInput, PhoneField } from "@/components/ui";
import { AuthHeader, BackLink, FooterLink, FormError, FormSuccess } from "@/components/brand";
import { DEFAULT_DIAL_CODE, prettyPhone, validatePhone } from "@/lib/phone";
import { theme } from "@/theme/theme";

type Step = "form" | "code";

const OTP_LENGTH = 4;
const CODE_TTL_SECONDS = 300;
const RESEND_COOLDOWN_SECONDS = 30;

function formatClock(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Account creation — phone number only.
 *
 * There is no password: the number is verified with a 4-digit code and the
 * account is created the moment that code is accepted. The same endpoint signs
 * an existing number in, which is exactly the "phone number is the only login
 * identifier" behaviour the client asked for.
 */
export default function RegisterScreen() {
  const router = useRouter();
  const { t } = useI18n();
  const { requestPhoneOtp, verifyPhoneOtp } = useAuth();

  const [step, setStep] = useState<Step>("form");
  const [name, setName] = useState("");
  const [dial, setDial] = useState(DEFAULT_DIAL_CODE);
  const [national, setNational] = useState("");
  const [sendingTo, setSendingTo] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);
  const [code, setCode] = useState<string[]>(["", "", "", ""]);
  const [countdown, setCountdown] = useState(CODE_TTL_SECONDS);
  const [resendCooldown, setResendCooldown] = useState(RESEND_COOLDOWN_SECONDS);

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

  const handleSendCode = async () => {
    setError(null);
    setInfo(null);

    const check = validatePhone(national, dial);
    if (!check.valid || !check.e164) {
      setError(t(check.errorKey ?? "phoneAuth.errInvalid"));
      return;
    }

    setLoading(true);
    const result = await requestPhoneOtp(check.e164, "register", name);
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

  const handleVerify = async () => {
    setError(null);
    const entered = code.join("");
    if (entered.length !== OTP_LENGTH) {
      setError(t("phoneAuth.errOtpIncomplete"));
      return;
    }
    if (!sendingTo) {
      setStep("form");
      return;
    }
    setLoading(true);
    const result = await verifyPhoneOtp(sendingTo, entered, name, requestId);
    setLoading(false);
    if (result.success) router.replace("/(tabs)/home");
    else setError(result.error || t("phoneAuth.errVerify"));
  };

  return (
    <KeyboardAvoidingView style={styles.fill} behavior={Platform.OS === "android" ? undefined : "padding"}>
      <ScrollView style={styles.fill} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <AuthHeader
          title={t(step === "form" ? "auth.register.titleForm" : "phoneAuth.otpTitle")}
          subtitle={step === "form" ? t("phoneAuth.subtitle") : undefined}
        />

        <FormError message={error || ""} />
        {info && !error ? <FormSuccess message={info} /> : null}

        {step === "form" ? (
          <View style={styles.formWrap}>
            <Input
              label={t("phoneAuth.nameLabel")}
              placeholder={t("phoneAuth.namePlaceholder")}
              value={name}
              onChangeText={setName}
              disabled={loading}
            />
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
              label={t("auth.register.emailFallback")}
              variant="outline"
              onPress={() => router.push("/(auth)/register-email")}
              disabled={loading}
            />
          </View>
        ) : (
          <View style={styles.formWrap}>
            <BackLink label={t("auth.register.editDetails")} onPress={() => setStep("form")} />
            <Text style={styles.otpSubtitle}>
              {t("phoneAuth.otpSubtitle", { phone: prettyPhone(sendingTo, dial) })}
            </Text>
            <OtpInput value={code} onChange={setCode} disabled={loading} length={OTP_LENGTH} />
            <Text style={styles.countdown}>
              {t("phoneAuth.expiresIn", { time: formatClock(countdown) })}
            </Text>
            <Pressable onPress={resendCooldown > 0 ? undefined : handleSendCode} disabled={resendCooldown > 0}>
              <Text style={[styles.resend, resendCooldown > 0 && styles.resendDisabled]}>
                {resendCooldown > 0
                  ? t("phoneAuth.resendIn", { seconds: resendCooldown })
                  : t("phoneAuth.resend")}
              </Text>
            </Pressable>
            <Button label={t("phoneAuth.create")} onPress={handleVerify} loading={loading} />
            {error ? (
              <Button
                label={t("phoneAuth.retry")}
                variant="outline"
                onPress={handleVerify}
                loading={loading}
              />
            ) : null}
          </View>
        )}

        <FooterLink
          prompt={t("auth.register.footerPrompt")}
          action={t("auth.register.footerAction")}
          onPress={() => router.replace("/(auth)/login")}
        />

        {/* Public About access — no account required. */}
        <View style={styles.aboutBlock}>
          <Text style={styles.aboutSection}>{t("aboutPublic.section")}</Text>
          <Button
            label={t("aboutPublic.cta")}
            variant="outline"
            icon={<Info size={16} color={theme.colors.primary} />}
            onPress={() => router.push("/about")}
            disabled={loading}
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: theme.spacing.xl, gap: theme.spacing.lg, paddingBottom: 60 },
  formWrap: { gap: theme.spacing.md },
  hint: { fontSize: 12, color: theme.colors.textMuted, lineHeight: 17 },
  otpSubtitle: { fontSize: 13, color: theme.colors.textSecondary, lineHeight: 18 },
  countdown: { textAlign: "center", color: theme.colors.textMuted, fontSize: 13 },
  resend: { textAlign: "center", color: theme.colors.primary, fontWeight: "600", fontSize: 13 },
  resendDisabled: { color: theme.colors.textMuted },
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
});
