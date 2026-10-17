import { createFileRoute, Link } from "@tanstack/react-router";
import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import {
  Sprout, Leaf, Cpu, TrendingUp, ShieldCheck, Layers, ChevronDown,
  ArrowRight, ShieldAlert, Sparkles, MapPin, Droplets, Wind,
  ThermometerSun, Compass, Crosshair, Zap, CheckCircle2, AlertTriangle,
  Truck, Radio, RefreshCw, BarChart3, Atom, Menu, X, Globe, Eye,
  Activity, ArrowUpRight, CloudSun, CloudRain, Lock, Info, Play, Volume2, VolumeX
} from "lucide-react";
import { KARNATAKA_DISTRICTS_DATA, DistrictData } from "@/components/seediq/karnataka-map";
import { DISTRICT_SEED_INTELLIGENCE, getRiskColorTheme } from "@/lib/seed-intelligence";

export const Route = createFileRoute("/")({
  component: SeedIQHomepage,
  head: () => ({
    meta: [
      { title: "SeedIQ — Hybrid AI + Quantum Machine Learning for Smart Agriculture" },
      { name: "description", content: "Next-generation agricultural intelligence platform combining classical machine learning and simulated quantum machine learning for crop selection, yield forecasting, seed viability analysis, and district-level decision support." },
    ],
  }),
});

/* -------------------------------------------------------------------------- */
/* Dynamic Animated Quantum-Bio Canvas Background                             */
/* -------------------------------------------------------------------------- */
function DynamicAtmosphere() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    // Particle nodes with gentle floating wave physics
    const particleCount = Math.min(Math.floor((width * height) / 14000), 85);
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.45,
      vy: (Math.random() - 0.5) * 0.45,
      radius: Math.random() * 2.0 + 0.8,
      baseRadius: Math.random() * 2.0 + 0.8,
      opacity: Math.random() * 0.5 + 0.2,
      pulseSpeed: Math.random() * 0.03 + 0.01,
      angle: Math.random() * Math.PI * 2,
      isQuantumNode: Math.random() > 0.7,
    }));

    let time = 0;

    const render = () => {
      time += 0.015;
      ctx.clearRect(0, 0, width, height);

      // 1. Undulating glowing energy wave gradients
      const grad1 = ctx.createRadialGradient(
        width * 0.3 + Math.sin(time * 0.5) * 120,
        height * 0.3 + Math.cos(time * 0.4) * 80,
        20,
        width * 0.3,
        height * 0.3,
        width * 0.5
      );
      grad1.addColorStop(0, "rgba(16, 185, 129, 0.08)");
      grad1.addColorStop(1, "transparent");
      ctx.fillStyle = grad1;
      ctx.fillRect(0, 0, width, height);

      const grad2 = ctx.createRadialGradient(
        width * 0.75 + Math.cos(time * 0.4) * 100,
        height * 0.65 + Math.sin(time * 0.6) * 90,
        10,
        width * 0.75,
        height * 0.65,
        width * 0.45
      );
      grad2.addColorStop(0, "rgba(6, 182, 212, 0.06)");
      grad2.addColorStop(1, "transparent");
      ctx.fillStyle = grad2;
      ctx.fillRect(0, 0, width, height);

      // 2. Interconnect filaments between close nodes
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 130) {
            const alpha = (1 - dist / 130) * 0.16;
            ctx.strokeStyle = particles[i].isQuantumNode
              ? `rgba(52, 211, 153, ${alpha})`
              : `rgba(56, 189, 248, ${alpha})`;
            ctx.lineWidth = 0.75;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }

      // 3. Render and update particles
      particles.forEach((p) => {
        p.angle += p.pulseSpeed;
        p.radius = p.baseRadius + Math.sin(p.angle) * 0.8;

        p.x += p.vx + Math.sin(p.angle) * 0.2;
        p.y += p.vy + Math.cos(p.angle) * 0.2;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        if (p.isQuantumNode) {
          ctx.fillStyle = `rgba(52, 211, 153, ${p.opacity * 1.5})`;
          ctx.shadowBlur = 10;
          ctx.shadowColor = "#34d399";
        } else {
          ctx.fillStyle = `rgba(147, 197, 253, ${p.opacity})`;
          ctx.shadowBlur = 4;
          ctx.shadowColor = "#38bdf8";
        }
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0 h-full w-full opacity-70"
    />
  );
}

/* -------------------------------------------------------------------------- */
/* Main SeedIQ Homepage Component                                             */
/* -------------------------------------------------------------------------- */
function SeedIQHomepage() {
  const { user, logout } = useAuth();
  const targetRoute = user ? "/dashboard" : "/login";
  const [showIntroVideo, setShowIntroVideo] = useState(true);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [selectedDistrictId, setSelectedDistrictId] = useState<string>("Mandya");
  const [activeCircuitQubit, setActiveCircuitQubit] = useState<number>(0);
  const [activeAlertTab, setActiveAlertTab] = useState<"rainfall" | "heat" | "seed">("seed");
  const videoRef = useRef<HTMLVideoElement>(null);

  // Parallax mouse coordinates
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const { innerWidth, innerHeight } = window;
      const x = (e.clientX / innerWidth - 0.5) * 25;
      const y = (e.clientY / innerHeight - 0.5) * 25;
      setMousePos({ x, y });
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  // District Selection Data
  const selectedDistrict: DistrictData =
    KARNATAKA_DISTRICTS_DATA[selectedDistrictId] || KARNATAKA_DISTRICTS_DATA["Mandya"];
  const selectedSeedInfo =
    DISTRICT_SEED_INTELLIGENCE[selectedDistrictId] || DISTRICT_SEED_INTELLIGENCE["Mandya"];

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <div className="relative min-h-screen w-full bg-[#020704] text-slate-100 selection:bg-emerald-500 selection:text-black font-sans overflow-x-hidden">
      
      {/* -------------------------------------------------------------------- */}
      {/* INITIAL CINEMATIC INTRO VIDEO OVERLAY                                */}
      {/* -------------------------------------------------------------------- */}
      <AnimatePresence>
        {showIntroVideo && (
          <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, scale: 1.05 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black overflow-hidden"
          >
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              onEnded={() => setShowIntroVideo(false)}
              className="absolute inset-0 h-full w-full object-cover opacity-90"
            >
              <source src="/intro_plant.mp4" type="video/mp4" />
            </video>

            {/* Subtle cinematic gradient vignette */}
            <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-black/60 pointer-events-none" />

            {/* Top Brand Banner during Intro */}
            <div className="absolute top-8 left-8 flex items-center gap-3 z-10 pointer-events-none">
              <div className="h-10 w-10 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 grid place-items-center text-emerald-400 backdrop-blur-md">
                <Sprout className="h-5 w-5 animate-pulse" />
              </div>
              <div>
                <span className="font-display text-xl font-bold tracking-tight text-white">
                  SEED<span className="text-emerald-400">IQ</span>
                </span>
                <p className="text-[9px] font-mono tracking-widest text-emerald-300 uppercase">
                  HYBRID AI + QUANTUM INTELLIGENCE
                </p>
              </div>
            </div>

            {/* Skip Intro CTA Button */}
            <button
              onClick={() => setShowIntroVideo(false)}
              className="absolute bottom-8 right-8 z-10 flex items-center gap-2 px-5 py-2.5 rounded-full bg-black/60 hover:bg-emerald-500 hover:text-black border border-white/20 text-xs font-mono font-bold text-white uppercase tracking-widest backdrop-blur-xl transition-all hover:scale-105 shadow-[0_0_30px_rgba(0,0,0,0.8)] cursor-pointer"
            >
              <span>SKIP INTRO</span>
              <X className="h-3.5 w-3.5" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* -------------------------------------------------------------------- */}
      {/* LIVING BACKGROUND ATMOSPHERE (Moving Landscape + Dynamic Canvas)    */}
      {/* -------------------------------------------------------------------- */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        
        {/* Dynamic Panoramic Karnataka Landscape with Slow Parallax Movement */}
        <div
          className="absolute inset-0 bg-cover bg-center opacity-30 scale-110 transition-transform duration-1000 ease-out"
          style={{
            backgroundImage: "url('/karnataka_panoramic_landscape.jpg')",
            transform: `translate3d(${mousePos.x * 0.6}px, ${mousePos.y * 0.6}px, 0) scale(1.08)`,
            willChange: "transform",
          }}
        />

        {/* Ambient Dark Green Gradient Vignette */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#020704]/70 via-[#020704]/85 to-[#020704]" />
        
        {/* Dynamic Bio-Quantum Particle & Wave Canvas */}
        <DynamicAtmosphere />
      </div>

      {/* ==================================================================== */}
      {/* 1. NAVIGATION BAR                                                    */}
      {/* ==================================================================== */}
      <nav className="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-6 py-4 md:px-12 backdrop-blur-2xl bg-black/40 border-b border-white/5 transition-all">
        
        {/* Logo / Brandmark */}
        <Link to="/" className="flex items-center gap-2.5 group">
          <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-emerald-400/20 to-emerald-600/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.25)] group-hover:border-emerald-400 transition-colors">
            <Sprout className="h-5 w-5" />
            <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
          </div>
          <div className="flex flex-col">
            <span className="font-display text-xl font-bold tracking-tight text-white flex items-center gap-1">
              SEED<span className="text-emerald-400">IQ</span>
            </span>
            <span className="text-[9px] font-mono tracking-widest uppercase text-emerald-400/80 -mt-1">
              HYBRID AI × QUANTUM
            </span>
          </div>
        </Link>

        {/* Center Desktop Navigation */}
        <div className="hidden md:flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1.5 backdrop-blur-md">
          <Link
            to={targetRoute}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors"
          >
            Dashboard
          </Link>
          <button
            onClick={() => scrollToSection("intelligence-section")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            AI Intelligence
          </button>
          <button
            onClick={() => scrollToSection("quantum-section")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            Quantum ML
          </button>
          <button
            onClick={() => scrollToSection("karnataka-map-section")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            Karnataka
          </button>
          <button
            onClick={() => scrollToSection("early-warning-section")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            Early Warnings
          </button>
          <button
            onClick={() => scrollToSection("pipeline-section")}
            className="px-4 py-1.5 rounded-full text-xs font-semibold text-white/80 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            Pipeline
          </button>
        </div>

        {/* Right CTA / Auth Buttons */}
        <div className="hidden md:flex items-center gap-3">
          <button
            onClick={() => setShowIntroVideo(true)}
            title="Replay Cinematic Intro"
            className="px-3 py-2 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 text-xs text-white/80 hover:text-emerald-400 flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <Play className="h-3 w-3 fill-current" />
            <span className="text-[11px] font-mono">Intro</span>
          </button>

          {user ? (
            <div className="flex items-center gap-2.5">
              <Link
                to="/dashboard"
                className="group relative flex items-center gap-2 rounded-full border border-emerald-400/40 bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-2 text-xs font-bold text-black shadow-[0_0_25px_rgba(16,185,129,0.35)] hover:shadow-[0_0_35px_rgba(16,185,129,0.5)] transition-all"
              >
                <span>Dashboard</span>
                <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
              </Link>
              <button
                onClick={() => logout()}
                className="px-3.5 py-2 rounded-full border border-white/10 bg-white/5 hover:bg-rose-950/40 hover:border-rose-500/40 text-xs text-white/70 hover:text-rose-300 transition-all cursor-pointer"
                title="Sign out of SeedIQ"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <>
              <Link
                to="/login"
                className="px-4 py-2 text-xs font-semibold text-white/80 hover:text-white transition-colors"
              >
                Sign In
              </Link>
              <Link
                to="/login"
                className="group relative flex items-center gap-2 rounded-full border border-emerald-400/40 bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-2 text-xs font-bold text-black shadow-[0_0_25px_rgba(16,185,129,0.35)] hover:shadow-[0_0_35px_rgba(16,185,129,0.5)] transition-all"
              >
                <span>Get Started</span>
                <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </>
          )}
        </div>

        {/* Mobile Menu Button */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/5 text-white"
          aria-label="Toggle Menu"
        >
          {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="fixed inset-x-0 top-[73px] z-30 bg-black/95 border-b border-white/10 p-6 backdrop-blur-2xl md:hidden space-y-4"
          >
            <div className="flex flex-col space-y-3 text-sm font-medium">
              <Link to={targetRoute} onClick={() => setMobileMenuOpen(false)} className="py-2 text-white/90">
                {user ? "Dashboard" : "Sign In to Dashboard"}
              </Link>
              <button onClick={() => scrollToSection("intelligence-section")} className="py-2 text-left text-white/90">
                AI Intelligence
              </button>
              <button onClick={() => scrollToSection("quantum-section")} className="py-2 text-left text-white/90">
                Quantum ML
              </button>
              <button onClick={() => scrollToSection("karnataka-map-section")} className="py-2 text-left text-white/90">
                Karnataka
              </button>
              <button onClick={() => scrollToSection("early-warning-section")} className="py-2 text-left text-white/90">
                Early Warnings
              </button>
              <button onClick={() => scrollToSection("pipeline-section")} className="py-2 text-left text-white/90">
                Decision Pipeline
              </button>
            </div>
            <div className="pt-4 border-t border-white/10 flex flex-col gap-3">
              {user ? (
                <>
                  <Link
                    to="/dashboard"
                    onClick={() => setMobileMenuOpen(false)}
                    className="w-full text-center py-2.5 rounded-xl bg-emerald-500 text-black text-xs font-bold shadow-lg"
                  >
                    Go to Dashboard
                  </Link>
                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      logout();
                    }}
                    className="w-full text-center py-2 rounded-xl border border-white/10 text-xs text-rose-300 font-semibold"
                  >
                    Sign Out
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    onClick={() => setMobileMenuOpen(false)}
                    className="w-full text-center py-2.5 rounded-xl border border-white/10 text-xs font-semibold"
                  >
                    Sign In
                  </Link>
                  <Link
                    to="/login"
                    onClick={() => setMobileMenuOpen(false)}
                    className="w-full text-center py-2.5 rounded-xl bg-emerald-500 text-black text-xs font-bold shadow-lg"
                  >
                    Get Started
                  </Link>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ==================================================================== */}
      {/* 2. HERO / ENTRANCE SCENE                                            */}
      {/* ==================================================================== */}
      <section className="relative min-h-screen w-full flex flex-col justify-center items-center px-6 pt-28 pb-16 text-center overflow-hidden z-10">
        
        {/* Hero Central Content */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          className="relative z-10 max-w-4xl mx-auto flex flex-col items-center"
        >
          {/* Top Tagline Pill */}
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-950/40 px-4 py-1.5 text-xs font-mono font-medium text-emerald-300 backdrop-blur-md shadow-[0_0_20px_rgba(16,185,129,0.2)] mb-8">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]" />
            <span>HYBRID AI + QUANTUM INTELLIGENCE FOR SMART AGRICULTURE</span>
          </div>

          {/* Main Title: SEEDIQ */}
          <h1 className="font-serif text-6xl sm:text-7xl md:text-9xl font-normal tracking-tight text-white drop-shadow-[0_20px_50px_rgba(0,0,0,0.8)] leading-none">
            SEED<span className="text-emerald-400 italic">IQ</span>
          </h1>

          {/* Subheading */}
          <h2 className="mt-4 font-display text-base sm:text-xl md:text-2xl font-semibold tracking-wider text-slate-200 uppercase">
            Transforming Agricultural Data into Intelligent Decisions
          </h2>

          {/* Supporting Paragraph */}
          <p className="mt-6 max-w-2xl text-sm sm:text-base text-slate-300/80 leading-relaxed font-normal">
            SeedIQ unifies classical machine learning with simulated quantum variational circuits to deliver precise crop recommendations, yield forecasting, seed germination viability modeling, and district-level decision support across Karnataka.
          </p>

          {/* CTA Buttons */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              to={targetRoute}
              className="group relative flex items-center gap-2.5 rounded-2xl bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-500 hover:from-emerald-400 hover:to-teal-300 text-black px-8 py-4 font-display text-sm font-bold shadow-[0_0_35px_rgba(16,185,129,0.35)] hover:shadow-[0_0_50px_rgba(16,185,129,0.55)] transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <span>{user ? "EXPLORE SEEDIQ" : "GET STARTED"}</span>
              <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
            </Link>

            <button
              onClick={() => scrollToSection("intelligence-section")}
              className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 hover:bg-white/10 hover:border-emerald-500/40 text-slate-200 px-7 py-4 font-display text-sm font-semibold backdrop-blur-md transition-all hover:scale-[1.02] cursor-pointer"
            >
              <span>VIEW INTELLIGENCE</span>
              <ChevronDown className="h-4 w-4 text-emerald-400" />
            </button>
          </div>
        </motion.div>

        {/* Hero Telemetry Metrics Strip */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.2 }}
          className="relative z-10 mt-16 grid grid-cols-2 md:grid-cols-4 gap-3 max-w-4xl w-full"
        >
          <div className="p-4 rounded-2xl border border-white/10 bg-black/40 backdrop-blur-xl text-left">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 text-emerald-400" />
              Coverage
            </div>
            <div className="font-display text-2xl font-bold text-white mt-1">31 Districts</div>
            <div className="text-[11px] text-emerald-400/90 mt-0.5">Karnataka Micro-Climates</div>
          </div>

          <div className="p-4 rounded-2xl border border-white/10 bg-black/40 backdrop-blur-xl text-left">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              Viability Model
            </div>
            <div className="font-display text-2xl font-bold text-white mt-1">98.4%</div>
            <div className="text-[11px] text-emerald-400/90 mt-0.5">Germination Accuracy</div>
          </div>

          <div className="p-4 rounded-2xl border border-white/10 bg-black/40 backdrop-blur-xl text-left">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Atom className="h-3.5 w-3.5 text-emerald-400" />
              Quantum ML
            </div>
            <div className="font-display text-2xl font-bold text-white mt-1">4-Qubit</div>
            <div className="text-[11px] text-emerald-400/90 mt-0.5">Variational Kernel</div>
          </div>

          <div className="p-4 rounded-2xl border border-white/10 bg-black/40 backdrop-blur-xl text-left">
            <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Truck className="h-3.5 w-3.5 text-emerald-400" />
              Objective 3
            </div>
            <div className="font-display text-2xl font-bold text-white mt-1">Adaptive</div>
            <div className="text-[11px] text-emerald-400/90 mt-0.5">Seed Redistribution</div>
          </div>
        </motion.div>
      </section>

      {/* ==================================================================== */}
      {/* 5. SCENE 2 — AGRICULTURAL INTELLIGENCE (Crop, Yield, Seed AI)       */}
      {/* ==================================================================== */}
      <section id="intelligence-section" className="relative py-28 px-6 md:px-12 max-w-7xl mx-auto z-10">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="text-[11px] font-mono font-bold uppercase tracking-[0.25em] text-emerald-400 mb-2">
            AI-DRIVEN AGRICULTURAL PRECISION
          </div>
          <h2 className="font-serif text-4xl sm:text-5xl md:text-6xl font-normal text-white tracking-tight">
            INTELLIGENCE <span className="italic text-emerald-300">BEYOND</span> THE FIELD
          </h2>
          <p className="mt-4 text-sm sm:text-base text-slate-300/80 leading-relaxed">
            SeedIQ combines classical machine learning and simulated quantum machine learning to transform agricultural data into practical intelligence.
          </p>
        </div>

        {/* 3 Premium Floating Glass Intelligence Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          
          {/* CARD 1: CROP AI */}
          <div className="group relative rounded-3xl border border-emerald-500/20 bg-gradient-to-b from-white/[0.04] to-black/80 p-6 backdrop-blur-2xl transition-all duration-300 hover:border-emerald-500/50 hover:shadow-[0_20px_60px_rgba(16,185,129,0.2)] hover:-translate-y-1.5 flex flex-col justify-between overflow-hidden">
            <div className="absolute top-0 right-0 h-48 w-48 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />
            
            <div>
              <div className="relative h-48 w-full rounded-2xl overflow-hidden border border-white/10 mb-6 bg-black/40">
                <img
                  src="/crops/rice/crop.webp"
                  alt="Crop AI Recommendation"
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-700"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
                <div className="absolute bottom-3 left-3 flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-emerald-500/90 text-black text-[10px] font-bold font-mono uppercase">
                    Soil Matrix AI
                  </span>
                </div>
              </div>

              <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-emerald-400">
                RECOMMENDATION ENGINE
              </div>
              <h3 className="font-display text-2xl font-bold text-white mt-1">CROP AI</h3>
              
              <p className="mt-3 text-xs text-slate-300 leading-relaxed">
                Smart multi-variable crop recommendation analyzing nitrogen (N), phosphorus (P), potassium (K), pH, annual rainfall, temperature, and ambient humidity across 22+ agricultural crop species.
              </p>

              <div className="mt-4 pt-3 border-t border-white/10 space-y-1.5 text-[11px] text-muted-foreground font-mono">
                <div className="flex justify-between">
                  <span>Soil Parameters:</span>
                  <span className="text-white">N-P-K-pH Balance</span>
                </div>
                <div className="flex justify-between">
                  <span>Climatic Factors:</span>
                  <span className="text-white">Rainfall & Humidity</span>
                </div>
                <div className="flex justify-between">
                  <span>Accuracy:</span>
                  <span className="text-emerald-400 font-bold">99.2% Test F1</span>
                </div>
              </div>
            </div>

            <Link
              to={user ? "/crop-ai" : "/login"}
              className="mt-6 flex items-center justify-between p-3 rounded-xl border border-white/10 bg-white/5 hover:bg-emerald-500/15 hover:border-emerald-500/40 text-xs font-semibold text-white transition-all group-hover:text-emerald-300"
            >
              <span>{user ? "Explore Crop AI Model" : "Sign In to Access Crop AI"}</span>
              <ArrowRight className="h-4 w-4 text-emerald-400 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

          {/* CARD 2: YIELD AI */}
          <div className="group relative rounded-3xl border border-emerald-500/20 bg-gradient-to-b from-white/[0.04] to-black/80 p-6 backdrop-blur-2xl transition-all duration-300 hover:border-emerald-500/50 hover:shadow-[0_20px_60px_rgba(16,185,129,0.2)] hover:-translate-y-1.5 flex flex-col justify-between overflow-hidden">
            <div className="absolute top-0 right-0 h-48 w-48 rounded-full bg-sky-500/10 blur-3xl pointer-events-none" />
            
            <div>
              <div className="relative h-48 w-full rounded-2xl overflow-hidden border border-white/10 mb-6 bg-black/40">
                <img
                  src="/crops/wheat/crop.webp"
                  alt="Yield AI Forecasting"
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-700"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
                <div className="absolute bottom-3 left-3 flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-sky-500/90 text-black text-[10px] font-bold font-mono uppercase">
                    Harvest Forecast
                  </span>
                </div>
              </div>

              <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-sky-400">
                PRODUCTION FORECASTER
              </div>
              <h3 className="font-display text-2xl font-bold text-white mt-1">YIELD AI</h3>
              
              <p className="mt-3 text-xs text-slate-300 leading-relaxed">
                Predict expected harvest production in metric tons/hectare using historical multi-season agricultural data, agro-climatic zones, seasonal precipitation, and fertilizer intensity indices.
              </p>

              <div className="mt-4 pt-3 border-t border-white/10 space-y-1.5 text-[11px] text-muted-foreground font-mono">
                <div className="flex justify-between">
                  <span>Ensemble:</span>
                  <span className="text-white">XGBoost + CatBoost</span>
                </div>
                <div className="flex justify-between">
                  <span>Input Granularity:</span>
                  <span className="text-white">State, Season & Area</span>
                </div>
                <div className="flex justify-between">
                  <span>Target Metric:</span>
                  <span className="text-sky-400 font-bold">Yield (Tons/Ha)</span>
                </div>
              </div>
            </div>

            <Link
              to={user ? "/yield-ai" : "/login"}
              className="mt-6 flex items-center justify-between p-3 rounded-xl border border-white/10 bg-white/5 hover:bg-sky-500/15 hover:border-sky-500/40 text-xs font-semibold text-white transition-all group-hover:text-sky-300"
            >
              <span>{user ? "Explore Yield AI Model" : "Sign In to Access Yield AI"}</span>
              <ArrowRight className="h-4 w-4 text-sky-400 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

          {/* CARD 3: SEED AI & STORAGE */}
          <div className="group relative rounded-3xl border border-emerald-500/20 bg-gradient-to-b from-white/[0.04] to-black/80 p-6 backdrop-blur-2xl transition-all duration-300 hover:border-emerald-500/50 hover:shadow-[0_20px_60px_rgba(16,185,129,0.2)] hover:-translate-y-1.5 flex flex-col justify-between overflow-hidden">
            <div className="absolute top-0 right-0 h-48 w-48 rounded-full bg-amber-500/10 blur-3xl pointer-events-none" />
            
            <div>
              <div className="relative h-48 w-full rounded-2xl overflow-hidden border border-white/10 mb-6 bg-black/40">
                <img
                  src="/crops/tomato/storage.webp"
                  alt="Seed AI Storage & Regeneration"
                  loading="lazy"
                  decoding="async"
                  className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-700"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/30 to-transparent" />
                <div className="absolute bottom-3 left-3 flex items-center gap-2">
                  <span className="px-2.5 py-1 rounded-full bg-emerald-400 text-black text-[10px] font-bold font-mono uppercase">
                    Objective 3 Engine
                  </span>
                </div>
              </div>

              <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-emerald-400">
                VIABILITY & REDISTRIBUTION
              </div>
              <h3 className="font-display text-2xl font-bold text-white mt-1">SEED AI</h3>
              
              <p className="mt-3 text-xs text-slate-300 leading-relaxed">
                Analyze seed germination viability curves, assess micro-climate storage risk, and power adaptive seed regeneration and regional stock redistribution before seasonal planting deadlines.
              </p>

              <div className="mt-4 pt-3 border-t border-white/10 space-y-1.5 text-[11px] text-muted-foreground font-mono">
                <div className="flex justify-between">
                  <span>Decay Horizon:</span>
                  <span className="text-white">90–180 Day Curve</span>
                </div>
                <div className="flex justify-between">
                  <span>Decision Logic:</span>
                  <span className="text-white">Regenerate vs Redistribute</span>
                </div>
                <div className="flex justify-between">
                  <span>Storage Metrics:</span>
                  <span className="text-emerald-400 font-bold">Rh, Thermal & Pest</span>
                </div>
              </div>
            </div>

            <Link
              to={user ? "/seed-ai" : "/login"}
              className="mt-6 flex items-center justify-between p-3 rounded-xl border border-white/10 bg-white/5 hover:bg-emerald-500/15 hover:border-emerald-500/40 text-xs font-semibold text-white transition-all group-hover:text-emerald-300"
            >
              <span>{user ? "Explore Seed AI Engine" : "Sign In to Access Seed AI"}</span>
              <ArrowRight className="h-4 w-4 text-emerald-400 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 6. SCENE 3 — QUANTUM + AI (Simulated QML & 4-Qubit Kernel)          */}
      {/* ==================================================================== */}
      <section id="quantum-section" className="relative py-28 px-6 md:px-12 max-w-7xl mx-auto z-10 border-t border-white/5">
        
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          
          {/* Left Description Column */}
          <div className="lg:col-span-5 space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-950/40 px-3.5 py-1 text-xs font-mono font-medium text-emerald-400">
              <Atom className="h-3.5 w-3.5 animate-spin text-emerald-400" />
              <span>SIMULATED QUANTUM KERNEL</span>
            </div>

            <h2 className="font-serif text-4xl sm:text-5xl font-normal text-white tracking-tight leading-tight">
              CLASSICAL AI <br />
              <span className="italic text-emerald-300">×</span> QUANTUM INTELLIGENCE
            </h2>

            <p className="text-sm text-slate-300 leading-relaxed">
              SeedIQ explores hybrid intelligence by combining classical machine learning with simulated quantum models to evaluate complex agricultural patterns across high-dimensional feature spaces.
            </p>

            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="grid h-8 w-8 place-items-center rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-mono text-xs font-bold shrink-0">
                  01
                </div>
                <div>
                  <div className="font-display text-xs font-bold text-white">Agricultural Feature State</div>
                  <div className="text-[11px] text-muted-foreground">Soil NPK, temperature, humidity, storage aging</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="grid h-8 w-8 place-items-center rounded-xl bg-sky-500/10 border border-sky-500/30 text-sky-400 font-mono text-xs font-bold shrink-0">
                  02
                </div>
                <div>
                  <div className="font-display text-xs font-bold text-white">4-Qubit Variational Encoding</div>
                  <div className="text-[11px] text-muted-foreground">Angle encoding & parameterized Ry/Rz quantum rotations</div>
                </div>
              </div>

              <div className="flex items-center gap-3 p-3 rounded-2xl bg-white/[0.02] border border-white/10">
                <div className="grid h-8 w-8 place-items-center rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 font-mono text-xs font-bold shrink-0">
                  03
                </div>
                <div>
                  <div className="font-display text-xs font-bold text-white">Hybrid Meta-Learner Decision</div>
                  <div className="text-[11px] text-muted-foreground">Actionable crop selection & seed viability advisory</div>
                </div>
              </div>
            </div>
          </div>

          {/* Right Interactive Quantum Circuit Simulation Visualizer */}
          <div className="lg:col-span-7 rounded-3xl border border-emerald-500/30 bg-[#040e08]/95 p-6 md:p-8 backdrop-blur-3xl shadow-[0_25px_80px_rgba(0,0,0,0.9)] relative overflow-hidden">
            
            <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-6">
              <div>
                <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400">
                  HYBRID VQC SIMULATOR
                </span>
                <h3 className="font-display text-xl font-bold text-white">4-Qubit Entanglement Circuit</h3>
              </div>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-950/80 px-3 py-1 rounded-full border border-emerald-500/30 flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                State: Superposition
              </span>
            </div>

            <div className="space-y-4 font-mono text-xs">
              
              {/* Qubit 0 */}
              <div
                onClick={() => setActiveCircuitQubit(0)}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer ${
                  activeCircuitQubit === 0 ? "border-emerald-500/50 bg-emerald-950/30" : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <span className="font-bold text-emerald-400 w-10">|q₀⟩</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-white font-bold">H</span>
                <div className="h-0.5 flex-1 bg-emerald-500/40 relative">
                  <span className="absolute left-1/4 -top-2.5 px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 text-[9px] text-emerald-300">Ry(θ₁)</span>
                  <span className="absolute left-1/2 -top-1.5 h-3 w-3 rounded-full bg-emerald-400" />
                </div>
                <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/40 text-[9px] text-sky-300">Rz(φ₁)</span>
                <span className="text-[10px] text-muted-foreground font-sans">Soil Nitrogen State</span>
              </div>

              {/* Qubit 1 */}
              <div
                onClick={() => setActiveCircuitQubit(1)}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer ${
                  activeCircuitQubit === 1 ? "border-emerald-500/50 bg-emerald-950/30" : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <span className="font-bold text-emerald-400 w-10">|q₁⟩</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-white font-bold">H</span>
                <div className="h-0.5 flex-1 bg-emerald-500/40 relative">
                  <span className="absolute left-1/4 -top-2.5 px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 text-[9px] text-emerald-300">Ry(θ₂)</span>
                  <span className="absolute left-1/2 -top-2 h-4 w-4 grid place-items-center rounded-full border border-emerald-400 text-[10px] font-bold text-emerald-400">⊕</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/40 text-[9px] text-sky-300">Rz(φ₂)</span>
                <span className="text-[10px] text-muted-foreground font-sans">Phosphorus State</span>
              </div>

              {/* Qubit 2 */}
              <div
                onClick={() => setActiveCircuitQubit(2)}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer ${
                  activeCircuitQubit === 2 ? "border-emerald-500/50 bg-emerald-950/30" : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <span className="font-bold text-emerald-400 w-10">|q₂⟩</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-white font-bold">H</span>
                <div className="h-0.5 flex-1 bg-emerald-500/40 relative">
                  <span className="absolute left-1/4 -top-2.5 px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 text-[9px] text-emerald-300">Ry(θ₃)</span>
                  <span className="absolute left-3/4 -top-1.5 h-3 w-3 rounded-full bg-emerald-400" />
                </div>
                <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/40 text-[9px] text-sky-300">Rz(φ₃)</span>
                <span className="text-[10px] text-muted-foreground font-sans">Thermal Index</span>
              </div>

              {/* Qubit 3 */}
              <div
                onClick={() => setActiveCircuitQubit(3)}
                className={`flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer ${
                  activeCircuitQubit === 3 ? "border-emerald-500/50 bg-emerald-950/30" : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <span className="font-bold text-emerald-400 w-10">|q₃⟩</span>
                <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-white font-bold">H</span>
                <div className="h-0.5 flex-1 bg-emerald-500/40 relative">
                  <span className="absolute left-1/4 -top-2.5 px-2 py-0.5 rounded bg-emerald-950 border border-emerald-500/40 text-[9px] text-emerald-300">Ry(θ₄)</span>
                  <span className="absolute left-3/4 -top-2 h-4 w-4 grid place-items-center rounded-full border border-emerald-400 text-[10px] font-bold text-emerald-400">⊕</span>
                </div>
                <span className="px-2 py-0.5 rounded bg-sky-950 border border-sky-500/40 text-[9px] text-sky-300">Rz(φ₄)</span>
                <span className="text-[10px] text-muted-foreground font-sans">Moisture Gradient</span>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-white/10 grid grid-cols-3 gap-3 text-center">
              <div className="p-2.5 rounded-xl bg-black/50 border border-white/5">
                <div className="text-[9px] font-mono uppercase text-muted-foreground">Quantum Fidelity</div>
                <div className="text-sm font-bold text-emerald-400 mt-0.5">99.82%</div>
              </div>
              <div className="p-2.5 rounded-xl bg-black/50 border border-white/5">
                <div className="text-[9px] font-mono uppercase text-muted-foreground">Circuit Depth</div>
                <div className="text-sm font-bold text-white mt-0.5">14 Layers</div>
              </div>
              <div className="p-2.5 rounded-xl bg-black/50 border border-white/5">
                <div className="text-[9px] font-mono uppercase text-muted-foreground">Entanglement Mode</div>
                <div className="text-sm font-bold text-sky-300 mt-0.5">Full Ring Topology</div>
              </div>
            </div>

          </div>

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 7. SCENE 4 — KARNATAKA AGRICULTURAL INTELLIGENCE (Map & Panel)      */}
      {/* ==================================================================== */}
      <section id="karnataka-map-section" className="relative py-28 px-6 md:px-12 max-w-7xl mx-auto z-10 border-t border-white/5">
        
        {/* Section Header */}
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="text-[11px] font-mono font-bold uppercase tracking-[0.25em] text-emerald-400 mb-2">
            DISTRICT-LEVEL SPATIAL REASONING
          </div>
          <h2 className="font-serif text-4xl sm:text-5xl md:text-6xl font-normal text-white tracking-tight">
            KARNATAKA AGRICULTURAL <span className="italic text-emerald-300">INTELLIGENCE</span>
          </h2>
          <p className="mt-4 text-sm sm:text-base text-slate-300/80 leading-relaxed">
            Explore authentic micro-climates, soil compositions, primary crop lines, and seed viability assessments across all 31 administrative districts.
          </p>
        </div>

        {/* Map Layout: Interactive Map + District Glass Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Left: Interactive Real Karnataka SVG Map */}
          <div className="lg:col-span-7 rounded-3xl border border-emerald-500/25 bg-gradient-to-b from-[#081710]/90 via-[#030a07]/95 to-black p-6 backdrop-blur-2xl shadow-2xl relative">
            
            <div className="flex items-center justify-between border-b border-white/10 pb-4 mb-4">
              <div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400">
                  GEOGRAPHICAL DISTRICT MAP
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  Click any district to inspect agricultural profile & early warning diagnostics
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-950/60 px-3 py-1 rounded-full border border-emerald-500/30">
                <Compass className="h-3.5 w-3.5" />
                31 Districts
              </div>
            </div>

            {/* SVG Karnataka Map */}
            <div className="relative flex items-center justify-center py-4">
              <svg viewBox="0 0 460 700" className="w-full h-[520px] select-none">
                <defs>
                  <filter id="hpSonarGlow" x="-30%" y="-30%" width="160%" height="160%">
                    <feGaussianBlur stdDeviation="4" result="blur" />
                    <feComposite in="SourceGraphic" in2="blur" operator="over" />
                  </filter>
                </defs>

                {/* District Paths */}
                <g>
                  {Object.entries(KARNATAKA_DISTRICTS_DATA).map(([key, district]) => {
                    const isSelected = selectedDistrictId === key;
                    const dSeed = DISTRICT_SEED_INTELLIGENCE[key];
                    const rTheme = dSeed ? getRiskColorTheme(dSeed.riskLevel) : getRiskColorTheme("STABLE");

                    return (
                      <g
                        key={district.id}
                        onClick={() => setSelectedDistrictId(key)}
                        className="cursor-pointer transition-all duration-200 focus:outline-none"
                        tabIndex={0}
                        role="button"
                        aria-label={district.name}
                      >
                        <path
                          d={district.path}
                          fill={isSelected ? rTheme.stroke : rTheme.fill}
                          fillOpacity={isSelected ? 0.95 : 0.8}
                          stroke={isSelected ? "#ffffff" : rTheme.stroke}
                          strokeWidth={isSelected ? 2.2 : 1.1}
                          strokeLinejoin="round"
                          filter={isSelected ? "url(#hpSonarGlow)" : undefined}
                          className="transition-all duration-300 hover:fill-emerald-500/60"
                        />
                        <text
                          x={district.labelX}
                          y={district.labelY}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          fontSize={isSelected ? "9.5" : "7.5"}
                          fontWeight={isSelected ? "800" : "600"}
                          fill={isSelected ? "#ffffff" : "#cbd5e1"}
                          className="pointer-events-none drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]"
                        >
                          {district.name}
                        </text>
                      </g>
                    );
                  })}
                </g>

                {/* Radar ring on selected district */}
                {selectedDistrict && (
                  <g transform={`translate(${selectedDistrict.labelX}, ${selectedDistrict.labelY})`} className="pointer-events-none">
                    <circle r="20" fill="none" stroke="#34d399" strokeWidth="1.5" className="animate-ping" />
                  </g>
                )}
              </svg>
            </div>

            {/* Map Legend */}
            <div className="mt-4 pt-3 border-t border-white/10 flex flex-wrap items-center justify-between text-[11px] font-mono text-muted-foreground gap-2">
              <div className="flex items-center gap-4">
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" /> Critical</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-500" /> Warning</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-yellow-400" /> Monitor</span>
                <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-400" /> Stable</span>
              </div>
              <span className="text-emerald-400 font-bold">Selected: {selectedDistrict.name}</span>
            </div>
          </div>

          {/* Right: Premium Glass District Information Panel */}
          <div className="lg:col-span-5 rounded-3xl border border-emerald-500/25 bg-gradient-to-b from-[#081710]/95 to-black p-6 backdrop-blur-2xl shadow-2xl space-y-5">
            
            {/* Header */}
            <div className="flex items-start justify-between border-b border-white/10 pb-4">
              <div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-emerald-400">
                  SELECTED DISTRICT ADVISORY
                </div>
                <h3 className="font-display text-3xl font-extrabold text-white mt-1">
                  {selectedDistrict.name.toUpperCase()}
                  <span className="text-xl font-normal text-emerald-300 ml-2">({selectedDistrict.kannadaName})</span>
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">{selectedDistrict.region}</p>
              </div>

              <div className="px-3 py-1 rounded-full bg-emerald-950 border border-emerald-500/40 text-emerald-400 font-mono text-xs font-bold">
                {selectedSeedInfo.riskLevel}
              </div>
            </div>

            {/* Seed Intelligence Card */}
            <div className="p-4 rounded-2xl bg-emerald-950/20 border border-emerald-500/25 space-y-2.5">
              <div className="flex items-center justify-between text-xs">
                <span className="font-mono text-emerald-400 uppercase font-bold text-[10px]">Seed Intelligence</span>
                <span className="text-slate-300">Crop: <strong className="text-white">{selectedSeedInfo.crop}</strong></span>
              </div>

              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className="p-2.5 rounded-xl bg-black/40 border border-white/5">
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">CURRENT VIABILITY</div>
                  <div className="text-2xl font-bold text-white mt-0.5">{selectedSeedInfo.currentViability}%</div>
                </div>
                <div className="p-2.5 rounded-xl bg-black/40 border border-white/5">
                  <div className="text-[9px] font-mono text-muted-foreground uppercase">90D PREDICTED</div>
                  <div className="text-2xl font-bold text-emerald-400 mt-0.5">{selectedSeedInfo.predictedViability}%</div>
                </div>
              </div>

              <p className="text-[11px] text-slate-200 italic pt-1">
                "{selectedSeedInfo.earlyWarning}"
              </p>
            </div>

            {/* Agricultural Profile */}
            <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/10 space-y-3 text-xs">
              <div className="text-[10px] font-mono font-bold uppercase text-emerald-400">
                AGRICULTURAL PROFILE
              </div>

              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <div className="text-[9px] uppercase text-muted-foreground font-mono">SOIL TYPE</div>
                  <div className="font-semibold text-white mt-0.5">{selectedDistrict.soilType}</div>
                </div>
                <div>
                  <div className="text-[9px] uppercase text-muted-foreground font-mono">AVG. RAINFALL</div>
                  <div className="font-semibold text-white mt-0.5">{selectedDistrict.rainfall}</div>
                </div>
                <div>
                  <div className="text-[9px] uppercase text-muted-foreground font-mono">SOWING</div>
                  <div className="font-semibold text-white mt-0.5">{selectedDistrict.sowingSeason}</div>
                </div>
              </div>

              <div className="pt-2 border-t border-white/10">
                <div className="text-[10px] text-muted-foreground font-mono mb-1.5">PRIMARY CROPS:</div>
                <div className="flex flex-wrap gap-1.5">
                  {[...selectedDistrict.primaryCropsCol1, ...selectedDistrict.primaryCropsCol2].slice(0, 4).map((c, i) => (
                    <span key={i} className="px-2.5 py-1 rounded-lg bg-black/40 border border-white/10 text-[11px] text-slate-200">
                      {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Agricultural Advisory */}
            <div className="p-4 rounded-2xl bg-black/60 border border-white/10">
              <div className="text-[10px] font-mono font-bold uppercase text-emerald-400 mb-1">
                ICAR & AGRI DEPT ADVISORY
              </div>
              <p className="text-xs text-slate-200 leading-relaxed">
                {selectedDistrict.advisory}
              </p>
            </div>

            <Link
              to={targetRoute}
              className="w-full py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-display font-bold text-xs flex items-center justify-center gap-2 transition-all shadow-lg"
            >
              <span>{user ? "Open Full District Intelligence Suite" : "Sign In to Access District Suite"}</span>
              <ArrowRight className="h-4 w-4" />
            </Link>

          </div>

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 8. OBJECTIVE 3 — AGRICULTURAL ALERT / EARLY WARNING SYSTEM          */}
      {/* ==================================================================== */}
      <section id="early-warning-section" className="relative py-28 px-6 md:px-12 max-w-7xl mx-auto z-10 border-t border-white/5">
        
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="inline-flex items-center gap-2 rounded-full border border-red-500/30 bg-red-950/40 px-3.5 py-1 text-xs font-mono font-medium text-red-400 mb-3">
            <ShieldAlert className="h-3.5 w-3.5" />
            <span>SEEDIQ OBJECTIVE 3 ADVISORY ENGINE</span>
          </div>
          <h2 className="font-serif text-4xl sm:text-5xl md:text-6xl font-normal text-white tracking-tight">
            EARLY WARNING <span className="italic text-emerald-300">FOR SMARTER</span> AGRICULTURE
          </h2>
          <div className="mt-4 flex items-center justify-center gap-2 font-mono text-xs font-bold text-emerald-400">
            <span>MONITOR</span>
            <span>→</span>
            <span>DETECT</span>
            <span>→</span>
            <span>ALERT</span>
            <span>→</span>
            <span>RECOMMEND</span>
          </div>
        </div>

        {/* 3 Interactive Alert Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          {/* Alert 1: Rainfall Alert */}
          <div
            onClick={() => setActiveAlertTab("rainfall")}
            className={`p-6 rounded-3xl border transition-all cursor-pointer ${
              activeAlertTab === "rainfall"
                ? "border-sky-500/50 bg-sky-950/20 shadow-[0_15px_50px_rgba(14,165,233,0.15)]"
                : "border-white/10 bg-white/[0.02] hover:border-white/20"
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="grid h-10 w-10 place-items-center rounded-2xl bg-sky-500/10 border border-sky-500/30 text-sky-400">
                <CloudRain className="h-5 w-5" />
              </div>
              <span className="text-[10px] font-mono font-bold uppercase text-sky-400 bg-sky-950 px-2.5 py-0.5 rounded-full border border-sky-500/30">
                Rainfall Alert
              </span>
            </div>
            <h3 className="font-display text-lg font-bold text-white">Precipitation & Drainage Stress</h3>
            <p className="mt-2 text-xs text-slate-300 leading-relaxed">
              Excessive rainfall conditions detected in coastal and malnad districts. High water table saturation threatens seedling root asphyxiation.
            </p>
            <div className="mt-4 pt-3 border-t border-white/10 text-[11px] text-sky-300 font-semibold flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Recommendation: Clear field drainage channels & withhold irrigation.
            </div>
          </div>

          {/* Alert 2: Heat Stress Alert */}
          <div
            onClick={() => setActiveAlertTab("heat")}
            className={`p-6 rounded-3xl border transition-all cursor-pointer ${
              activeAlertTab === "heat"
                ? "border-amber-500/50 bg-amber-950/20 shadow-[0_15px_50px_rgba(245,158,11,0.15)]"
                : "border-white/10 bg-white/[0.02] hover:border-white/20"
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="grid h-10 w-10 place-items-center rounded-2xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
                <ThermometerSun className="h-5 w-5" />
              </div>
              <span className="text-[10px] font-mono font-bold uppercase text-amber-400 bg-amber-950 px-2.5 py-0.5 rounded-full border border-amber-500/30">
                Heat Stress Alert
              </span>
            </div>
            <h3 className="font-display text-lg font-bold text-white">Thermal Anomaly & Evapotranspiration</h3>
            <p className="mt-2 text-xs text-slate-300 leading-relaxed">
              Ambient temperature spikes exceeding 36°C with low relative humidity in northern dry zones threaten floral abortion in pulses and cotton.
            </p>
            <div className="mt-4 pt-3 border-t border-white/10 text-[11px] text-amber-300 font-semibold flex items-center gap-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Recommendation: Deploy micro-sprinklers & apply anti-transpirants.
            </div>
          </div>

          {/* Alert 3: Seed Viability Alert */}
          <div
            onClick={() => setActiveAlertTab("seed")}
            className={`p-6 rounded-3xl border transition-all cursor-pointer ${
              activeAlertTab === "seed"
                ? "border-red-500/50 bg-red-950/20 shadow-[0_15px_50px_rgba(239,68,68,0.15)]"
                : "border-white/10 bg-white/[0.02] hover:border-white/20"
            }`}
          >
            <div className="flex items-center justify-between mb-4">
              <div className="grid h-10 w-10 place-items-center rounded-2xl bg-red-500/10 border border-red-500/30 text-red-400">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <span className="text-[10px] font-mono font-bold uppercase text-red-400 bg-red-950 px-2.5 py-0.5 rounded-full border border-red-500/30">
                Seed Viability Alert
              </span>
            </div>
            <h3 className="font-display text-lg font-bold text-white">Storage Decay & Stock Redistribution</h3>
            <p className="mt-2 text-xs text-slate-300 leading-relaxed">
              Storage relative humidity {">"}70% accelerating seed viability loss below 50% threshold. Immediate certified foundation stock transfer required.
            </p>
            <div className="mt-4 pt-3 border-t border-white/10 text-[11px] text-red-300 font-semibold flex items-center gap-1">
              <Truck className="h-3.5 w-3.5" /> Recommendation: Redistribute certified seed stock from Mysuru hub.
            </div>
          </div>

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 9. AI DECISION PIPELINE (Data to Decision)                          */}
      {/* ==================================================================== */}
      <section id="pipeline-section" className="relative py-28 px-6 md:px-12 max-w-7xl mx-auto z-10 border-t border-white/5">
        
        <div className="text-center max-w-3xl mx-auto mb-16">
          <div className="text-[11px] font-mono font-bold uppercase tracking-[0.25em] text-emerald-400 mb-2">
            END-TO-END NEURAL ARCHITECTURE
          </div>
          <h2 className="font-serif text-4xl sm:text-5xl md:text-6xl font-normal text-white tracking-tight">
            FROM DATA <span className="italic text-emerald-300">TO</span> DECISION
          </h2>
          <p className="mt-4 text-sm sm:text-base text-slate-300/80 leading-relaxed">
            The automated, transparent machine intelligence workflow transforming raw meteorological & soil inputs into reliable farm recommendations.
          </p>
        </div>

        {/* Responsive Pipeline Steps */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-center text-xs">
          
          {[
            { step: "01", name: "DATA", desc: "Soil, GPS, Weather" },
            { step: "02", name: "PREPROCESS", desc: "Imputation & Scale" },
            { step: "03", name: "CLASSICAL ML", desc: "XGBoost & CatBoost" },
            { step: "04", name: "QUANTUM ML", desc: "4-Qubit Simulator" },
            { step: "05", name: "META MODEL", desc: "Ensemble Fusion" },
            { step: "06", name: "PREDICTION", desc: "Viability & Yield" },
            { step: "07", name: "ALERT", desc: "Early Warning" },
            { step: "08", name: "DECISION", desc: "Action Advisory" },
          ].map((item, idx) => (
            <div
              key={idx}
              className="p-4 rounded-2xl border border-white/10 bg-black/50 backdrop-blur-xl flex flex-col justify-between hover:border-emerald-500/40 transition-colors group"
            >
              <div className="text-[10px] font-mono font-bold text-emerald-400">{item.step}</div>
              <div className="font-display font-bold text-white my-2 group-hover:text-emerald-300 transition-colors">
                {item.name}
              </div>
              <div className="text-[10px] text-muted-foreground">{item.desc}</div>
            </div>
          ))}

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 10. FINAL CALL TO ACTION                                             */}
      {/* ==================================================================== */}
      <section className="relative py-32 px-6 md:px-12 max-w-5xl mx-auto z-10 text-center">
        
        <div className="p-10 md:p-16 rounded-3xl border border-emerald-500/30 bg-gradient-to-b from-emerald-950/30 via-[#030e07]/90 to-black backdrop-blur-3xl shadow-[0_30px_100px_rgba(0,0,0,0.9)] relative overflow-hidden">
          
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 h-64 w-96 rounded-full bg-emerald-500/20 blur-3xl pointer-events-none" />

          <h2 className="font-serif text-5xl sm:text-6xl md:text-7xl font-normal text-white tracking-tight leading-tight">
            INTELLIGENCE <br />
            <span className="italic text-emerald-300">FOR EVERY</span> FIELD.
          </h2>

          <p className="mt-6 max-w-xl mx-auto text-sm sm:text-base text-slate-300/80 leading-relaxed font-normal">
            From crop selection to yield prediction, seed viability and agricultural alerts, SeedIQ brings intelligent decision support closer to the farmer.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              to={targetRoute}
              className="flex items-center gap-2 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-400 hover:from-emerald-400 hover:to-teal-300 text-black px-8 py-4 font-display text-sm font-bold shadow-[0_0_35px_rgba(16,185,129,0.35)] transition-all hover:scale-[1.02]"
            >
              <span>{user ? "OPEN DASHBOARD" : "EXPLORE SEEDIQ"}</span>
              <ArrowRight className="h-4 w-4" />
            </Link>

            <Link
              to={user ? "/dashboard" : "/login"}
              className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 hover:bg-white/10 text-white px-8 py-4 font-display text-sm font-semibold backdrop-blur-md transition-all"
            >
              <span>{user ? "WORKSPACE" : "GET STARTED"}</span>
            </Link>
          </div>

        </div>
      </section>

      {/* ==================================================================== */}
      {/* 11. FOOTER                                                           */}
      {/* ==================================================================== */}
      <footer className="relative border-t border-white/10 bg-black/80 py-12 px-6 md:px-12 text-xs text-muted-foreground z-10">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-lg bg-emerald-500/20 border border-emerald-500/40 grid place-items-center text-emerald-400">
              <Sprout className="h-3.5 w-3.5" />
            </div>
            <span className="font-display font-bold text-white text-sm">SeedIQ Platform</span>
            <span className="text-[10px] font-mono text-emerald-400/80 ml-2">v4.2 Hybrid Engine</span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-6 font-mono text-[11px]">
            <Link to={targetRoute} className="hover:text-emerald-400 transition-colors">Dashboard</Link>
            <Link to={user ? "/crop-ai" : "/login"} className="hover:text-emerald-400 transition-colors">Crop AI</Link>
            <Link to={user ? "/yield-ai" : "/login"} className="hover:text-emerald-400 transition-colors">Yield AI</Link>
            <Link to={user ? "/seed-ai" : "/login"} className="hover:text-emerald-400 transition-colors">Seed AI</Link>
            <Link to={user ? "/storage-ai" : "/login"} className="hover:text-emerald-400 transition-colors">Storage AI</Link>
            <Link to={user ? "/quantum" : "/login"} className="hover:text-emerald-400 transition-colors">Quantum QML</Link>
          </div>

          <div className="text-[11px] font-mono text-white/50">
            © 2026 SeedIQ. All rights reserved.
          </div>
        </div>
      </footer>

    </div>
  );
}
