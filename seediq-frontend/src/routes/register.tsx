import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import React, { useState, useRef, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Sparkles,
  User,
  Mail,
  Lock,
  ArrowRight,
  ShieldCheck,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  RefreshCw,
  ArrowLeft,
} from "lucide-react";

export const Route = createFileRoute("/register")({
  component: RegisterPage,
});

function RegisterPage() {
  const navigate = useNavigate();
  const { user, requestRegistrationOtp, verifyRegistrationOtp } = useAuth();

  // If user is already authenticated, redirect straight to dashboard
  useEffect(() => {
    if (user) {
      navigate({ to: "/dashboard" });
    }
  }, [user, navigate]);

  // Registration step: "form" | "otp"
  const [step, setStep] = useState<"form" | "otp">("form");

  // Form State
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // OTP State
  const [otpDigits, setOtpDigits] = useState<string[]>(["", "", "", "", "", ""]);
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);
  const [countdown, setCountdown] = useState(600); // 10 minutes (in seconds)
  const [resendCooldown, setResendCooldown] = useState(30);

  // UI State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Password rules validation
  const hasMinLength = password.length >= 8;
  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const hasSpecial = /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password);
  const passwordsMatch = password.length > 0 && password === confirmPassword;

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

  // Step 1: Submit registration details & request OTP
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    const trimmedName = name.trim();
    const trimmedEmail = email.trim().toLowerCase();

    if (!trimmedName) {
      setError("Please enter your full name.");
      return;
    }
    if (!trimmedEmail || !trimmedEmail.includes("@")) {
      setError("Please enter a valid Gmail / email address.");
      return;
    }
    if (passedRulesCount < 5) {
      setError("Please satisfy all password security requirements.");
      return;
    }
    if (!passwordsMatch) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    const result = await requestRegistrationOtp(trimmedName, trimmedEmail, password);
    setLoading(false);

    if (result.success) {
      setStep("otp");
      setCountdown(600);
      setResendCooldown(30);
      setSuccessMsg(result.message || `Verification code sent to ${trimmedEmail}`);
      setTimeout(() => inputRefs.current[0]?.focus(), 100);
    } else {
      setError(result.error || "Failed to initiate registration.");
    }
  };

  // OTP Box inputs handler
  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) {
      // Pasted full OTP
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

  // Step 2: Verify OTP & complete account creation
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const otp = otpDigits.join("");
    if (otp.length < 6) {
      setError("Please enter the complete 6-digit verification code.");
      return;
    }

    setLoading(true);
    const result = await verifyRegistrationOtp(email.trim().toLowerCase(), otp);
    setLoading(false);

    if (result.success) {
      navigate({ to: "/dashboard" });
    } else {
      setError(result.error || "Verification code is incorrect.");
    }
  };

  const handleResendOtp = async () => {
    if (resendCooldown > 0) return;
    setError(null);
    setSuccessMsg(null);
    setLoading(true);
    const result = await requestRegistrationOtp(name.trim(), email.trim().toLowerCase(), password);
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

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 md:p-8 overflow-hidden bg-[#020805] font-sans selection:bg-emerald-500/30">
      
      {/* Background Atmospheric Ambience */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-40 -right-40 w-[600px] h-[600px] bg-emerald-600/15 rounded-full blur-[140px] animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-[600px] h-[600px] bg-teal-600/15 rounded-full blur-[140px]" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(rgba(52, 211, 153, 0.4) 1px, transparent 1px)`,
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      {/* Main Dual-Column Showcase Card */}
      <div className="relative w-full max-w-4xl z-10 grid grid-cols-1 lg:grid-cols-12 rounded-3xl border border-emerald-500/25 bg-[#07130c]/90 backdrop-blur-3xl shadow-[0_25px_80px_rgba(0,0,0,0.9)] overflow-hidden">
        
        {/* Left Visual Artwork Panel (Large Screens) */}
        <div className="lg:col-span-5 relative hidden lg:flex flex-col justify-between p-8 overflow-hidden border-r border-emerald-500/20 bg-black/40">
          <img
            src="/auth_quantum_farm.jpg"
            alt="SeedIQ Quantum Agriculture"
            className="absolute inset-0 w-full h-full object-cover opacity-60 scale-105 transition-transform duration-1000 hover:scale-100"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#040c07] via-[#040c07]/40 to-transparent" />
          
          {/* Top Tag */}
          <div className="relative z-10">
            <Link to="/" className="inline-flex items-center gap-2 group">
              <div className="h-8 w-8 rounded-xl bg-emerald-500/20 border border-emerald-500/40 grid place-items-center text-emerald-400">
                <Sparkles className="h-4 w-4" />
              </div>
              <span className="font-display font-bold text-lg text-white">Seed<span className="text-emerald-400">IQ</span></span>
            </Link>
          </div>

          {/* Bottom Floating Stats */}
          <div className="relative z-10 space-y-3">
            <div className="p-3.5 rounded-2xl bg-black/60 border border-white/10 backdrop-blur-md">
              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400">
                AI + Quantum Platform
              </div>
              <p className="text-xs text-slate-200 mt-1">
                Access Karnataka 31-district micro-climate models, seed storage longevity prediction, and crop recommendations.
              </p>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground px-1">
              <span className="flex items-center gap-1 text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" /> 98.4% Accuracy
              </span>
              <span className="text-white">v4.2</span>
            </div>
          </div>
        </div>

        {/* Right Form Column */}
        <div className="lg:col-span-7 p-8 sm:p-10 flex flex-col justify-center relative">
          
          {/* Top Edge Glow */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400/50 to-transparent" />

          {/* Header */}
          <div className="mb-6">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono font-bold uppercase tracking-wider mb-2">
              <Sparkles className="w-3 h-3" />
              {step === "form" ? "NEW USER REGISTRATION" : "GMAIL VERIFICATION"}
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight font-display">
              {step === "form" ? "Create your SeedIQ account" : "Verify your email"}
            </h1>
            <p className="text-xs sm:text-sm text-emerald-100/60 mt-1 leading-relaxed">
              {step === "form"
                ? "Join the agricultural intelligence platform and unlock personalized AI-driven insights."
                : `We've sent a 6-digit verification code to ${email}. Enter the code below to verify your account.`}
            </p>
          </div>

          {/* Feedback Banners */}
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-rose-950/40 border border-rose-500/30 flex items-start gap-2.5 text-rose-300 text-xs sm:text-sm animate-in fade-in duration-200">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              <div className="flex-1">{error}</div>
            </div>
          )}

          {successMsg && !error && (
            <div className="mb-5 p-3 rounded-xl bg-emerald-950/40 border border-emerald-500/30 flex items-start gap-2.5 text-emerald-300 text-xs sm:text-sm animate-in fade-in duration-200">
              <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-emerald-400" />
              <div className="flex-1">{successMsg}</div>
            </div>
          )}

          {/* STEP 1: Registration Form */}
          {step === "form" && (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              {/* Full Name */}
              <div>
                <label className="block text-xs font-medium text-emerald-200/80 mb-1">
                  Full Name
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                    <User className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Enter your full name"
                    required
                    disabled={loading}
                    className="w-full pl-10 pr-4 py-2.5 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                </div>
              </div>

              {/* Gmail / Email */}
              <div>
                <label className="block text-xs font-medium text-emerald-200/80 mb-1">
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
                    className="w-full pl-10 pr-4 py-2.5 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                </div>
              </div>

              {/* Password */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-emerald-200/80">
                    Password
                  </label>
                  {password && (
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
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Create a strong password"
                    required
                    disabled={loading}
                    className="w-full pl-10 pr-10 py-2.5 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-emerald-400/50 hover:text-emerald-300 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Confirm Password */}
              <div>
                <label className="block text-xs font-medium text-emerald-200/80 mb-1">
                  Confirm Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm your password"
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

              {/* Password Requirements Checklist */}
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

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Create Account & Send Code</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* STEP 2: 6-Digit OTP Verification */}
          {step === "otp" && (
            <form onSubmit={handleVerifyOtp} className="space-y-6">
              {/* Back to Form Button */}
              <button
                type="button"
                onClick={() => setStep("form")}
                className="inline-flex items-center gap-1.5 text-xs text-emerald-400/80 hover:text-emerald-300 transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Edit details</span>
              </button>

              {/* 6 OTP Boxes */}
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

              {/* Countdown & Resend Section */}
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

              {/* Verify Button */}
              <button
                type="submit"
                disabled={loading || otpDigits.join("").length < 6}
                className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 cursor-pointer"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
                ) : (
                  <>
                    <span>Verify & Launch Platform</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          )}

          {/* Link to Sign In */}
          <div className="text-center mt-6 pt-5 border-t border-emerald-500/15">
            <p className="text-xs text-emerald-100/60">
              Already have an account?{" "}
              <Link
                to="/login"
                className="text-emerald-400 font-semibold hover:text-emerald-300 hover:underline transition-colors"
              >
                Sign In
              </Link>
            </p>
          </div>

          {/* Security Guarantee */}
          <div className="mt-6 pt-3 flex items-center justify-center gap-1.5 text-[11px] text-emerald-400/50">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400/70" />
            <span>Encrypted SeedIQ Farmer Account Registration</span>
          </div>
        </div>
      </div>
    </div>
  );
}
