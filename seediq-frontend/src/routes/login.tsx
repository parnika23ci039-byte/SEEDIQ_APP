import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import React, { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Sparkles,
  Lock,
  Mail,
  ArrowRight,
  ShieldCheck,
  UserCheck,
  AlertCircle,
  Eye,
  EyeOff,
  Compass,
  Sprout,
  Atom,
  CheckCircle2
} from "lucide-react";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { user, signIn, loginAsGuest } = useAuth();

  // If user is already authenticated, redirect straight to dashboard
  useEffect(() => {
    if (user) {
      navigate({ to: "/dashboard" });
    }
  }, [user, navigate]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError("Please enter your Gmail address.");
      return;
    }
    if (!trimmedEmail.includes("@")) {
      setError("Please enter a valid Gmail / email address.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    setLoading(true);
    const result = await signIn(trimmedEmail, password);
    setLoading(false);

    if (result.success) {
      navigate({ to: "/dashboard" });
    } else {
      setError(result.error || "Invalid email or password.");
    }
  };

  const handleGuestLogin = async () => {
    setLoading(true);
    setError(null);
    const result = await loginAsGuest();
    setLoading(false);
    if (result.success) {
      navigate({ to: "/dashboard" });
    } else {
      setError(result.error || "Unable to initialize Guest session.");
    }
  };

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 md:p-8 overflow-hidden bg-[#020805] font-sans selection:bg-emerald-500/30">
      
      {/* Background Atmospheric Glows */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-40 -left-40 w-[600px] h-[600px] bg-emerald-600/15 rounded-full blur-[140px] animate-pulse" />
        <div className="absolute -bottom-40 -right-40 w-[600px] h-[600px] bg-teal-600/15 rounded-full blur-[140px]" />
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `radial-gradient(rgba(52, 211, 153, 0.4) 1px, transparent 1px)`,
            backgroundSize: "28px 28px",
          }}
        />
      </div>

      {/* Main Container Card (Dual Column Showcase) */}
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
                <Sprout className="h-4 w-4" />
              </div>
              <span className="font-display font-bold text-lg text-white">Seed<span className="text-emerald-400">IQ</span></span>
            </Link>
          </div>

          {/* Bottom Floating Stats */}
          <div className="relative z-10 space-y-3">
            <div className="p-3.5 rounded-2xl bg-black/60 border border-white/10 backdrop-blur-md">
              <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400">
                <Atom className="h-3.5 w-3.5 animate-spin" />
                Hybrid Intelligence Core
              </div>
              <p className="text-xs text-slate-200 mt-1">
                Combining Classical ML & 4-Qubit Quantum Variational Kernels for Agricultural Decision Support.
              </p>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground px-1">
              <span className="flex items-center gap-1 text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" /> 31 Districts Modeled
              </span>
              <span className="text-white">v4.2 Engine</span>
            </div>
          </div>
        </div>

        {/* Right Form Column */}
        <div className="lg:col-span-7 p-8 sm:p-10 flex flex-col justify-center relative">
          
          {/* Subtle Top Edge Glow */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400/50 to-transparent" />

          {/* Header */}
          <div className="mb-6">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 text-[10px] font-mono font-bold uppercase tracking-wider mb-3">
              <Sparkles className="w-3 h-3" />
              SECURE AGRICULTURAL WORKSPACE
            </div>

            <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight font-display">
              Welcome back to SeedIQ
            </h1>
            <p className="text-xs sm:text-sm text-emerald-100/60 mt-1 leading-relaxed">
              Sign in to access your crop intelligence, yield models, and seed storage advisory.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-5 p-3.5 rounded-xl bg-rose-950/40 border border-rose-500/30 flex items-start gap-3 text-rose-300 text-xs sm:text-sm">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              <div className="flex-1">{error}</div>
            </div>
          )}

          {/* Login Form */}
          <form onSubmit={handleSignIn} className="space-y-4">
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

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-medium text-emerald-200/80">
                  Password
                </label>
                <Link
                  to="/forgot-password"
                  className="text-xs font-medium text-emerald-400 hover:text-emerald-300 hover:underline transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-400/50">
                  <Lock className="w-4 h-4" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  required
                  disabled={loading}
                  className="w-full pl-10 pr-11 py-3 bg-[#040a06]/90 border border-emerald-500/20 rounded-xl text-white placeholder-emerald-100/25 text-sm focus:outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400/30 transition-all"
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

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-black font-semibold text-sm rounded-xl shadow-[0_4px_20px_rgba(16,185,129,0.25)] hover:shadow-[0_6px_25px_rgba(16,185,129,0.35)] transition-all duration-200 flex items-center justify-center gap-2 group disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-black/40 border-t-black rounded-full animate-spin" />
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </>
              )}
            </button>
          </form>

          {/* Guest Login Option */}
          <div className="mt-4">
            <button
              type="button"
              onClick={handleGuestLogin}
              disabled={loading}
              className="w-full py-2.5 px-4 bg-white/5 hover:bg-white/10 border border-emerald-500/20 text-emerald-200/90 text-xs font-medium rounded-xl transition-all flex items-center justify-center gap-2"
            >
              <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span>Explore as Guest</span>
            </button>
          </div>

          {/* Create Account Link */}
          <div className="text-center mt-6 pt-4 border-t border-emerald-500/15">
            <p className="text-xs text-emerald-100/60">
              Don't have a SeedIQ account?{" "}
              <Link
                to="/register"
                className="text-emerald-400 font-semibold hover:text-emerald-300 hover:underline transition-colors"
              >
                Create an account
              </Link>
            </p>
          </div>

        </div>

      </div>

    </div>
  );
}
