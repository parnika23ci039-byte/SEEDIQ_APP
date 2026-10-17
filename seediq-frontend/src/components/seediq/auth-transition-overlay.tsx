import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  LogOut,
  Clock,
  Sparkles,
  Atom,
  CheckCircle2,
  Lock,
  Radio,
  Zap
} from "lucide-react";

export type AuthTransitionType = "login" | "logout" | "guest_expire" | null;

export interface AuthTransitionState {
  type: AuthTransitionType;
  message: string;
  userName?: string;
  userRole?: string;
}

interface AuthTransitionOverlayProps {
  transition: AuthTransitionState;
}

export function AuthTransitionOverlay({ transition }: AuthTransitionOverlayProps) {
  if (!transition.type) return null;

  const isLogin = transition.type === "login";
  const isLogout = transition.type === "logout";
  const isGuestExpire = transition.type === "guest_expire";

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
        className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/90 backdrop-blur-2xl p-4 selection:bg-transparent select-none"
      >
        {/* Atmospheric Ambient Glow */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div
            className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] rounded-full blur-[140px] ${
              isLogin
                ? "bg-emerald-500/20"
                : isLogout
                ? "bg-sky-500/20"
                : "bg-amber-500/25"
            }`}
          />
        </div>

        {/* Central Card */}
        <motion.div
          initial={{ scale: 0.9, y: 20, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          exit={{ scale: 0.95, opacity: 0 }}
          transition={{ type: "spring", stiffness: 350, damping: 25 }}
          className={`relative max-w-md w-full rounded-3xl p-8 text-center border shadow-[0_25px_80px_rgba(0,0,0,0.95)] ${
            isLogin
              ? "bg-[#05140b]/95 border-emerald-500/40 shadow-[0_0_60px_rgba(16,185,129,0.25)]"
              : isLogout
              ? "bg-[#040e14]/95 border-sky-500/30 shadow-[0_0_60px_rgba(14,165,233,0.2)]"
              : "bg-[#140f04]/95 border-amber-500/40 shadow-[0_0_60px_rgba(245,158,11,0.25)]"
          }`}
        >
          {/* Glowing Animated Icon Centerpiece */}
          <div className="relative mx-auto mb-6 w-24 h-24 flex items-center justify-center">
            
            {/* Spinning Concentric Quantum Rings */}
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 4, ease: "linear" }}
              className={`absolute inset-0 rounded-full border-2 border-dashed ${
                isLogin
                  ? "border-emerald-400/50"
                  : isLogout
                  ? "border-sky-400/50"
                  : "border-amber-400/50"
              }`}
            />
            <motion.div
              animate={{ rotate: -360 }}
              transition={{ repeat: Infinity, duration: 6, ease: "linear" }}
              className={`absolute inset-2 rounded-full border border-dotted ${
                isLogin
                  ? "border-emerald-300/40"
                  : isLogout
                  ? "border-sky-300/40"
                  : "border-amber-300/40"
              }`}
            />

            {/* Core Icon */}
            <div
              className={`relative z-10 w-16 h-16 rounded-2xl grid place-items-center shadow-lg ${
                isLogin
                  ? "bg-emerald-500/20 border border-emerald-400/60 text-emerald-400 shadow-[0_0_30px_rgba(16,185,129,0.5)]"
                  : isLogout
                  ? "bg-sky-500/20 border border-sky-400/60 text-sky-400 shadow-[0_0_30px_rgba(14,165,233,0.5)]"
                  : "bg-amber-500/20 border border-amber-400/60 text-amber-400 shadow-[0_0_30px_rgba(245,158,11,0.5)]"
              }`}
            >
              {isLogin && <ShieldCheck className="w-8 h-8 animate-pulse" />}
              {isLogout && <LogOut className="w-8 h-8 animate-pulse" />}
              {isGuestExpire && <Clock className="w-8 h-8 animate-pulse" />}
            </div>
          </div>

          {/* Subheader / Status Tag */}
          <div
            className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase tracking-widest mb-3 ${
              isLogin
                ? "bg-emerald-950/80 border border-emerald-500/40 text-emerald-300"
                : isLogout
                ? "bg-sky-950/80 border border-sky-500/40 text-sky-300"
                : "bg-amber-950/80 border border-amber-500/40 text-amber-300"
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full animate-ping ${
                isLogin ? "bg-emerald-400" : isLogout ? "bg-sky-400" : "bg-amber-400"
              }`}
            />
            {isLogin && "IDENTITY VERIFIED"}
            {isLogout && "SESSION TERMINATED"}
            {isGuestExpire && "PREVIEW TIME EXPIRED"}
          </div>

          {/* Main Title */}
          <h2 className="font-display text-2xl font-bold text-white tracking-tight">
            {isLogin && (transition.userName ? `Welcome, ${transition.userName}` : "Login Successful")}
            {isLogout && "Logging Out..."}
            {isGuestExpire && "Guest Limit Reached"}
          </h2>

          {/* Message */}
          <p className="mt-2 text-xs text-slate-300/80 leading-relaxed font-normal max-w-xs mx-auto">
            {transition.message}
          </p>

          {/* Progress Indicator Bar */}
          <div className="mt-6 w-full bg-white/5 rounded-full h-1.5 overflow-hidden p-0.5 border border-white/10">
            <motion.div
              initial={{ width: "0%" }}
              animate={{ width: "100%" }}
              transition={{ duration: 1.2, ease: "easeInOut" }}
              className={`h-full rounded-full ${
                isLogin
                  ? "bg-gradient-to-r from-emerald-500 to-teal-400 shadow-[0_0_10px_#10b981]"
                  : isLogout
                  ? "bg-gradient-to-r from-sky-500 to-blue-400 shadow-[0_0_10px_#0ea5e9]"
                  : "bg-gradient-to-r from-amber-500 to-orange-400 shadow-[0_0_10px_#f59e0b]"
              }`}
            />
          </div>

          {/* Telemetry / Security Note */}
          <div className="mt-4 flex items-center justify-center gap-2 text-[10px] font-mono text-muted-foreground">
            <Zap className="h-3 w-3 text-emerald-400" />
            {isLogin && "Initializing Neural Engine & Workspace"}
            {isLogout && "Purging Security Tokens & Local Cache"}
            {isGuestExpire && "5-Minute Preview Duration Complete"}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
