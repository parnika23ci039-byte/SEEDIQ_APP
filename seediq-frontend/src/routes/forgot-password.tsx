import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Sparkles,
  Mail,
  Lock,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  RefreshCw,
} from "lucide-react";

export const Route = createFileRoute("/forgot-password")({
  component: ForgotPasswordPage,
});

function ForgotPasswordPage() {
  const navigate = useNavigate();
  const { requestPasswordResetOtp, verifyPasswordResetOtp, resetPassword } = useAuth();

  // Recovery flow: "email" | "otp" | "new_password" | "success"
  const [step, setStep] = useState<"email" | "otp" | "new_password" | "success">("email");

  // State
  const [email, setEmail] = useState("");
  const [otpDigits, setOtpDigits] = useState<string[]>(["", "", "", "", "", ""]);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // Timers & feedback
  const [countdown, setCountdown] = useState(600);
  const [resendCooldown, setResendCooldown] = useState(30);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Password rules validation
  const hasMinLength = newPassword.length >= 8;
  const hasUpper = /[A-Z]/.test(newPassword);
  const hasLower = /[a-z]/.test(newPassword);
  const hasNumber = /[0-9]/.test(newPassword);
  const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(newPassword);
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

  const passedRulesCount = [hasMinLength, hasUpper, hasLower, hasNumber, hasSpecial].filter(Boolean).length;
  const passwordStrength =
    passedRulesCount <= 2 ? "Weak" : passedRulesCount <= 4 ? "Medium" : "Strong";
  const strengthColor =
    passedRulesCount <= 2
      ? "text-rose-400 bg-rose-500/20"
      : passedRulesCount <= 4
      ? "text-amber-400 bg-amber-500/20"
      : "text-emerald-400 bg-emerald-500/20";

  // Countdown timer for OTP
  useEffect(() => {
    if (step !== "otp") return;
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 0 ? prev - 1 : 0));
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [step]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  // Step 1: Request Password Reset OTP
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !trimmedEmail.includes("@")) {
      setError("Please enter a valid Gmail / email address.");
      return;
    }

    setLoading(true);
    const result = await requestPasswordResetOtp(trimmedEmail);
    setLoading(false);

    if (result.success) {
      setStep("otp");
      setCountdown(600);
      setResendCooldown(30);
      setSuccessMsg(result.message || `Password reset code sent to ${trimmedEmail}`);
      setTimeout(() => inputRefs.current[0]?.focus(), 100);
    } else {
      setError(result.error || "Unable to send reset code.");
    }
  };

  // OTP inputs handler
  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) {
      const pasted = value.replace(/\D/g, "").slice(0, 6);
      if (pasted.length > 0) {
        const nextDigits = [...otpDigits];
        for (let i = 0; i < 6; i++) {
          nextDigits[i] = pasted[i] || "";
        }
        setOtpDigits(nextDigits);
        const focusIdx = Math.min(pasted.length, 5);
        inputRefs.current[focusIdx]?.focus();
      }
      return;
    }

    const digit = value.replace(/\D/g, "");
    const nextDigits = [...otpDigits];
    nextDigits[index] = digit;
    setOtpDigits(nextDigits);

    if (digit && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Backspace" && !otpDigits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pastedData) {
      const nextDigits = [...otpDigits];
      for (let i = 0; i < 6; i++) {
        nextDigits[i] = pastedData[i] || "";
      }
      setOtpDigits(nextDigits);
      const focusIdx = Math.min(pastedData.length, 5);
      inputRefs.current[focusIdx]?.focus();
    }
  };

  // Step 2: Verify OTP
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const otp = otpDigits.join("");
    if (otp.length < 6) {
      setError("Please enter the complete 6-digit verification code.");
      return;
    }

    setLoading(true);
    const result = await verifyPasswordResetOtp(email.trim().toLowerCase(), otp);
    setLoading(false);

    if (result.success) {
      setStep("new_password");
      setError(null);
      setSuccessMsg("Identity verified. Please create your new password.");
    } else {
      setError(result.error || "Verification code is incorrect.");
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    const result = await requestPasswordResetOtp(email.trim().toLowerCase());
    setLoading(false);
    if (result.success) {
      setCountdown(600);
      setResendCooldown(30);
      setOtpDigits(["", "", "", "", "", ""]);
      setSuccessMsg("A new verification code has been dispatched.");
      inputRefs.current[0]?.focus();
    } else {
      setError(result.error || "Unable to resend code.");
    }
  };

  // Step 3: Update Password
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (passedRulesCount < 5) {
      setError("Please satisfy all password security requirements.");
      return;
    }
    if (!passwordsMatch) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    const otp = otpDigits.join("");
    const result = await resetPassword(email.trim().toLowerCase(), otp, newPassword);
    setLoading(false);

    if (result.success) {
      setStep("success");
    } else {
      setError(result.error || "Failed to update password.");
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 overflow-hidden bg-[#030906] font-sans selection:bg-emerald-500/30">
      {/* Ambience */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] bg-emerald-600/10 rounded-full blur-[140px] animate-pulse" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] bg-teal-600/10 rounded-full blur-[140px]" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(rgba(52, 211, 153, 0.4) 1px, transparent 1px)`,
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      {/* Main Card */}
      <div className="relative w-full max-w-[480px] z-10">
        <div className="bg-[#08130d]/80 backdrop-blur-2xl border border-emerald-500/20 rounded-3xl p-8 sm:p-10 shadow-[0_25px_70px_rgba(0,0,0,0.85)] relative overflow-hidden">
          {/* Top Edge Glow */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400/50 to-transparent" />

          {/* Header */}
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 mb-3 shadow-[0_0_25px_rgba(16,185,129,0.15)]">
              <Sparkles className="w-7 h-7" />
            </div>

            <div className="flex items-center justify-center gap-2 mb-1">
              <span className="text-2xl font-bold tracking-tight text-white">SeedIQ</span>
            </div>
            <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-emerald-400/90 mb-2">
              QUANTUM INTELLIGENCE FOR AGRICULTURE
            </p>

            <h1 className="text-xl sm:text-2xl font-semibold text-white tracking-tight">
              {step === "email" && "Reset your password"}
              {step === "otp" && "Verify your identity"}
              {step === "new_password" && "Create a new password"}
              {step === "success" && "Password updated"}
            </h1>

            <p className="text-xs sm:text-sm text-emerald-100/60 mt-1.5 leading-relaxed">
              {step === "email" &&
                "Enter your registered Gmail address and we'll send you a verification code."}
              {step === "otp" &&
                `Enter the verification code sent to ${email}.`}
              {step === "new_password" &&
                "Set a strong password for your SeedIQ account."}
              {step === "success" &&
                "Your password has been updated successfully. You can now sign in with your new credentials."}
            </p>
          </div>

          {/* Alerts */}
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 flex items-start gap-2.5 text-rose-300 text-xs sm:text-sm animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              <div className="flex-1">{error}</div>
            </div>
          )}

          {successMsg && !error && step !== "success" && (
            <div className="mb-5 p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-start gap-2.5 text-emerald-300 text-xs sm:text-sm animate-in fade-in duration-200">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
              <div className="flex-1">{successMsg}</div>
            </div>
          )}

          {/* STEP 1: Enter Gmail */}
          {step === "email" && (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-emerald-200/80 mb-1.5">
                  Email Address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your Gmail address"
                    required
                    disabled={loading}
                    className="w-full pl-10 pr-4 py-3 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Send Verification Code</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 2: Verify OTP */}
          {step === "otp" && (
            <form onSubmit={handleVerifyOtp} className="space-y-6">
              <button
                type="button"
                onClick={() => setStep("email")}
                className="inline-flex items-center gap-1.5 text-xs text-emerald-400/80 hover:text-emerald-300 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Change email</span>
              </button>

              <div className="flex items-center justify-center gap-2 sm:gap-3" onPaste={handlePaste}>
                {otpDigits.map((digit, index) => (
                  <input
                    key={index}
                    ref={(el) => (inputRefs.current[index] = el)}
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={1}
                    value={digit}
                    onChange={(e) => handleOtpChange(index, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(index, e)}
                    disabled={loading}
                    className="w-11 h-13 sm:w-12 sm:h-14 text-center text-xl sm:text-2xl font-bold bg-[#040c07] border-2 border-emerald-500/30 focus:border-emerald-400 focus:bg-[#06150b] rounded-xl text-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-400/30 transition-all shadow-inner"
                  />
                ))}
              </div>

              <div className="text-center space-y-2">
                <p className="text-xs text-emerald-200/60 font-mono">
                  ⏱️ Code expires in {formatTime(countdown)}
                </p>

                <div>
                  <button
                    type="button"
                    onClick={handleResendOtp}
                    disabled={resendCooldown > 0 || loading}
                    className="text-xs font-semibold text-emerald-400 hover:text-emerald-300 disabled:text-emerald-400/40 disabled:cursor-not-allowed transition-colors inline-flex items-center gap-1.5"
                  >
                    <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
                    {resendCooldown > 0
                      ? `Didn't receive the code? Resend in ${resendCooldown}s`
                      : "Didn't receive the code? Resend OTP"}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || otpDigits.join("").length < 6}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Verify Code</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 3: Create New Password */}
          {step === "new_password" && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-emerald-200/80">
                    New Password
                  </label>
                  {newPassword && (
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${strengthColor}`}>
                      {passwordStrength}
                    </span>
                  )}
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="Enter new password"
                    required
                    disabled={loading}
                    className="w-full pl-10 pr-10 py-2.5 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-emerald-400/50 hover:text-emerald-300 transition-colors"
                  >
                    {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-emerald-200/80 mb-1">
                  Confirm New Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm new password"
                    required
                    disabled={loading}
                    className="w-full pl-10 pr-10 py-2.5 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-emerald-400/50 hover:text-emerald-300 transition-colors"
                  >
                    {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div className="p-3 bg-[#040c07]/70 border border-emerald-500/15 rounded-xl space-y-1.5 text-[11px]">
                <p className="font-semibold text-emerald-200/70 mb-1">Password Requirements:</p>
                <div className="grid grid-cols-2 gap-1.5">
                  <div className={`flex items-center gap-1.5 ${hasMinLength ? "text-emerald-400" : "text-emerald-200/40"}`}>
                    {hasMinLength ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-emerald-200/30" />}
                    <span>At least 8 characters</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasUpper ? "text-emerald-400" : "text-emerald-200/40"}`}>
                    {hasUpper ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-emerald-200/30" />}
                    <span>One uppercase letter</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasLower ? "text-emerald-400" : "text-emerald-200/40"}`}>
                    {hasLower ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-emerald-200/30" />}
                    <span>One lowercase letter</span>
                  </div>
                  <div className={`flex items-center gap-1.5 ${hasNumber ? "text-emerald-400" : "text-emerald-200/40"}`}>
                    {hasNumber ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-emerald-200/30" />}
                    <span>One number</span>
                  </div>
                  <div className={`flex items-center gap-1.5 col-span-2 ${hasSpecial ? "text-emerald-400" : "text-emerald-200/40"}`}>
                    {hasSpecial ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <XCircle className="w-3 h-3 text-emerald-200/30" />}
                    <span>One special character (!@#$%^&*)</span>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Update Password</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 4: Success State */}
          {step === "success" && (
            <div className="text-center py-4 space-y-6">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                <CheckCircle2 className="w-9 h-9" />
              </div>
              <p className="text-sm text-emerald-100/80">
                Your password has been updated successfully.
              </p>
              <button
                type="button"
                onClick={() => navigate({ to: "/login" })}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                <span>Continue to Sign In</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Bottom Link to Sign In */}
          {step !== "success" && (
            <div className="text-center mt-6 pt-5 border-t border-emerald-500/15">
              <p className="text-xs text-emerald-100/60">
                Remember your password?{" "}
                <Link
                  to="/login"
                  className="text-emerald-400 font-semibold hover:text-emerald-300 hover:underline transition-colors"
                >
                  Sign In
                </Link>
              </p>
            </div>
          )}

          {/* Security Guarantee */}
          <div className="mt-6 pt-3 flex items-center justify-center gap-1.5 text-[11px] text-emerald-400/50">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400/70" />
            <span>Secure SeedIQ Password Recovery Protocol</span>
          </div>
        </div>
      </div>
    </div>
  );
}
