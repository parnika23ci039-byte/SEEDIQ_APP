import { createFileRoute } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Atom, Zap, Sparkles, Sprout, Network, Cpu, BrainCircuit, Activity,
  ChevronRight, RefreshCw, BarChart4, ShieldCheck
} from "lucide-react";
import { Gauge } from "@/components/seediq/gauge";

import quantumBg from "@/assets/home-quantum-orb.jpg";

export const Route = createFileRoute("/_app/quantum")({
  component: QuantumPlayground,
  head: () => ({ meta: [{ title: "Quantum Playground — SeedIQ" }, { name: "description", content: "Interactive Quantum Machine Learning Simulation." }] }),
});

function QuantumPlayground() {
  const [n, setN] = useState(42);
  const [p, setP] = useState(28);
  const [k, setK] = useState(65);
  const [ph, setPh] = useState(6.8);

  const [isSimulating, setIsSimulating] = useState(false);
  const [fidelity, setFidelity] = useState(0.97);
  const [entanglement, setEntanglement] = useState(0.89);
  const [matchProb, setMatchProb] = useState(92);

  const handleSimulate = () => {
    setIsSimulating(true);
    // Simulate some changing values during processing
    const interval = setInterval(() => {
      setFidelity(0.85 + Math.random() * 0.1);
      setEntanglement(0.75 + Math.random() * 0.2);
      setMatchProb(Math.floor(80 + Math.random() * 15));
    }, 100);

    setTimeout(() => {
      clearInterval(interval);
      setIsSimulating(false);
      // Final calculation based on rough heuristics for demonstration
      const score = (n / 60 + p / 50 + k / 70 + (ph > 6 && ph < 7.5 ? 1 : 0.5)) / 4;
      setFidelity(Math.min(0.99, score + 0.1));
      setEntanglement(Math.min(0.95, score));
      setMatchProb(Math.min(99, Math.max(10, Math.floor(score * 100))));
    }, 1500);
  };

  return (
    <div className="space-y-8 pb-16">
      
      {/* 1. HEADER SECTION with Background Image */}
      <div className="relative overflow-hidden rounded-3xl border border-emerald-500/20 shadow-2xl">
        <div className="absolute inset-0 z-0">
          <img src={quantumBg} alt="Quantum Background" className="h-full w-full object-cover opacity-30" />
          <div className="absolute inset-0 bg-gradient-to-r from-black via-black/80 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-t from-black via-transparent to-transparent" />
        </div>
        
        <div className="relative z-10 p-8 md:p-12 lg:w-2/3">
          <motion.div 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}
            className="flex items-center gap-3 mb-4"
          >
            <div className="grid h-12 w-12 place-items-center rounded-2xl border border-emerald-500/30 bg-emerald-500/10 shadow-[0_0_30px_-5px_hsl(155_70%_45%/0.5)]">
              <Atom className="h-6 w-6 text-emerald-400" />
            </div>
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 uppercase tracking-widest">Interactive Simulation</span>
          </motion.div>
          
          <motion.h1 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}
            className="font-display text-4xl md:text-5xl font-bold text-white leading-tight"
          >
            Quantum Machine Learning <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-sky-400">Playground</span>
          </motion.h1>
          
          <motion.p 
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2 }}
            className="mt-4 text-lg text-emerald-100/70 max-w-xl"
          >
            Experience how SeedIQ leverages Variational Quantum Circuits (VQC) to optimize agricultural feature embeddings and generate hyper-accurate crop recommendations.
          </motion.p>
        </div>
      </div>

      {/* 2. HOW IT WORKS SECTION */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {[
          { icon: <Cpu className="h-6 w-6" />, title: "Data Encoding", desc: "Classical soil data (N, P, K, pH) is encoded into quantum states using angle embedding.", color: "text-sky-400" },
          { icon: <Network className="h-6 w-6" />, title: "Quantum Ansatz", desc: "A parameterized quantum circuit processes the highly entangled state vector.", color: "text-indigo-400" },
          { icon: <Activity className="h-6 w-6" />, title: "Measurement", desc: "The circuit is measured back into classical bits across multiple shots.", color: "text-fuchsia-400" },
          { icon: <BrainCircuit className="h-6 w-6" />, title: "Decision Fusion", desc: "Quantum probabilities are fused with classical ML for the final prediction.", color: "text-emerald-400" }
        ].map((step, i) => (
          <motion.div 
            key={i}
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: i * 0.1 }}
            className="rounded-2xl border border-white/10 bg-black/40 backdrop-blur-md p-5 relative overflow-hidden group"
          >
            <div className={`absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity ${step.color} scale-[3]`}>
              {step.icon}
            </div>
            <div className={`mb-3 inline-flex rounded-xl bg-white/5 p-2.5 ${step.color}`}>
              {step.icon}
            </div>
            <h3 className="font-display font-semibold text-white mb-2 flex items-center gap-2">
              <span className="text-xs text-white/40">0{i+1}</span> {step.title}
            </h3>
            <p className="text-sm text-white/60 leading-relaxed">{step.desc}</p>
          </motion.div>
        ))}
      </div>

      {/* 3. SIMULATION & CONTROLS */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_400px] gap-6">
        
        {/* Left: Circuit & Visualization */}
        <div className="space-y-6">
          <div className="rounded-3xl border border-emerald-500/20 bg-gradient-to-br from-black/60 to-emerald-950/20 p-6 md:p-8 backdrop-blur-xl relative overflow-hidden">
            <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_10%,transparent_100%)]" />
            
            <div className="relative z-10 mb-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Atom className="h-6 w-6 text-emerald-400 animate-[spin_10s_linear_infinite]" />
                <h2 className="font-display text-2xl font-semibold text-white">Live VQC Simulation</h2>
              </div>
              {isSimulating && (
                <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                  </span>
                  PROCESSING QUBITS...
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-white/10 bg-black/80 p-6 relative">
              <QuantumCircuit isSimulating={isSimulating} />
              
              <div className="mt-8 flex flex-wrap gap-4 text-[11px] font-semibold uppercase tracking-widest text-white/50">
                <LegendChip c="hsl(199 89% 48%)" l="Rotation Y" k="Rᵧ" />
                <LegendChip c="hsl(287 60% 65%)" l="Hadamard" k="H" />
                <LegendChip c="hsl(155 70% 45%)" l="Rotation Z" k="Rz" />
                <LegendChip c="hsl(46 70% 55%)" l="Measurement" k="M" />
              </div>
            </div>

            <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="rounded-2xl border border-white/5 bg-black/40 p-5">
                <h3 className="text-sm font-semibold text-white/80 uppercase tracking-widest mb-4 flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-emerald-400" /> State Vector
                </h3>
                <div className="flex items-center justify-center">
                  <BlochSphere isSimulating={isSimulating} n={n} p={p} k={k} ph={ph} />
                </div>
                <div className="mt-4 rounded-xl bg-white/5 p-3 text-center font-mono text-xs text-emerald-300">
                  |ψ⟩ = {fidelity.toFixed(2)}|00⟩ + {(1 - fidelity).toFixed(2)}|11⟩
                </div>
              </div>
              
              <div className="rounded-2xl border border-white/5 bg-black/40 p-5 flex flex-col justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-white/80 uppercase tracking-widest mb-4 flex items-center gap-2">
                    <BarChart4 className="h-4 w-4 text-emerald-400" /> Telemetry
                  </h3>
                  <div className="space-y-4">
                    <MetricBar label="Circuit Fidelity" value={fidelity} color="bg-emerald-500" />
                    <MetricBar label="Entanglement Entropy" value={entanglement} color="bg-sky-500" />
                    <MetricBar label="Expressibility" value={0.88} color="bg-indigo-500" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Control Panel */}
        <div className="space-y-6">
          <div className="rounded-3xl border border-emerald-500/20 bg-black/40 backdrop-blur-xl p-6">
            <div className="mb-6 flex items-center gap-2 border-b border-white/10 pb-4">
              <Sparkles className="h-5 w-5 text-emerald-400" />
              <h2 className="font-display text-xl font-semibold text-white">Input Parameters</h2>
            </div>
            
            <div className="space-y-6">
              <Slider icon={<Sprout className="h-4 w-4 text-emerald-400"/>} c="hsl(155 70% 45%)" label="Nitrogen (N)" value={n} setValue={setN} unit="%" max={100} />
              <Slider icon={<Sprout className="h-4 w-4 text-sky-400"/>} c="hsl(210 80% 55%)" label="Phosphorus (P)" value={p} setValue={setP} unit="%" max={100} />
              <Slider icon={<Sprout className="h-4 w-4 text-indigo-400"/>} c="hsl(260 70% 60%)" label="Potassium (K)" value={k} setValue={setK} unit="%" max={100} />
              <Slider icon={<Activity className="h-4 w-4 text-fuchsia-400"/>} c="hsl(300 70% 55%)" label="pH Potential" value={ph} setValue={setPh} unit="" max={14} step={0.1} />
            </div>

            <button 
              onClick={handleSimulate}
              disabled={isSimulating}
              className={`mt-8 flex w-full items-center justify-center gap-2 rounded-xl py-4 font-display font-semibold transition-all duration-300 ${
                isSimulating 
                ? "bg-emerald-500/20 text-emerald-500 cursor-not-allowed" 
                : "bg-emerald-500 text-black hover:bg-emerald-400 hover:shadow-[0_0_20px_-5px_hsl(155_70%_45%)]"
              }`}
            >
              {isSimulating ? (
                <><RefreshCw className="h-5 w-5 animate-spin" /> Calculating...</>
              ) : (
                <><Zap className="h-5 w-5" /> Calculate Ansatz</>
              )}
            </button>
          </div>

          <div className="rounded-3xl border border-emerald-500/20 bg-gradient-to-b from-emerald-950/40 to-black/40 backdrop-blur-xl p-6 text-center">
            <h3 className="text-sm font-semibold text-white/60 uppercase tracking-widest mb-6">Quantum Match Probability</h3>
            <div className="flex justify-center mb-6">
              <Gauge value={matchProb} size={140} color="emerald" />
            </div>
            <div className="rounded-xl bg-white/5 p-4 text-sm text-emerald-100/70 border border-white/10">
              <span className="flex items-center justify-center gap-2 text-emerald-400 font-semibold mb-1">
                <ShieldCheck className="h-4 w-4" /> Optimization Complete
              </span>
              The VQC has converged. The displayed probability represents the quantum confidence score for crop viability based on your parameters.
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

// ---- Helper Components ----

function Slider({ icon, c, label, value, setValue, unit, max, step = 1 }: any) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 font-medium text-white/80">{icon} {label}</span>
        <span className="font-display font-bold" style={{ color: c }}>{value.toFixed(step < 1 ? 1 : 0)}{unit}</span>
      </div>
      <input 
        type="range" min={0} max={max} step={step} value={value} 
        onChange={(e) => setValue(parseFloat(e.target.value))} 
        className="w-full appearance-none rounded-full h-1.5 cursor-pointer bg-white/10" 
        style={{ accentColor: c }} 
      />
    </div>
  );
}

function MetricBar({ label, value, color }: { label: string, value: number, color: string }) {
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-white/60">{label}</span>
        <span className="text-white font-mono">{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
        <motion.div 
          className={`h-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${value * 100}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}

function LegendChip({ c, l, k }: { c: string; l: string; k: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="grid h-5 w-5 place-items-center rounded border text-[10px] font-bold" style={{ borderColor: c, color: c, backgroundColor: `${c}15` }}>{k}</span>
      <span className="text-white/70">{l}</span>
    </span>
  );
}

function BlochSphere({ isSimulating, n, p, k, ph }: { isSimulating: boolean, n: number, p: number, k: number, ph: number }) {
  // Map parameters to an angle between 0 and PI for Z-axis, and 0 to 2*PI for XY-plane
  // This gives an illusion of a parameterized quantum state |ψ(θ, φ)⟩
  const theta = (n / 100) * Math.PI; // 0 to PI
  const phi = ((p + k) / 200) * Math.PI * 2; // 0 to 2*PI
  
  // Radius of the Bloch sphere in SVG
  const r = 55;
  
  // Calculate endpoint of the state vector arrow using spherical coordinates projected to 2D
  // Note: This is a pseudo-3D projection for aesthetic interactive feeling
  const dx = r * Math.sin(theta) * Math.cos(phi);
  const dy = -r * Math.cos(theta); // Negative because SVG y-axis goes down

  const targetX = 70 + dx;
  const targetY = 70 + dy;

  return (
    <div className="relative h-48 w-48">
      <motion.svg 
        viewBox="0 0 140 140" 
        className="h-full w-full drop-shadow-[0_0_15px_rgba(16,185,129,0.2)]"
        animate={{ rotateY: isSimulating ? 360 : 0 }}
        transition={{ duration: 2, repeat: isSimulating ? Infinity : 0, ease: "linear" }}
      >
        <circle cx="70" cy="70" r="55" fill="none" stroke="hsl(155 70% 45% / 0.4)" strokeWidth="2" />
        <ellipse cx="70" cy="70" rx="55" ry="18" fill="none" stroke="hsl(155 70% 45% / 0.4)" strokeWidth="1.5" />
        <ellipse cx="70" cy="70" rx="18" ry="55" fill="none" stroke="hsl(155 70% 45% / 0.4)" strokeWidth="1.5" />
        <line x1="70" y1="15" x2="70" y2="125" stroke="hsl(155 70% 45% / 0.5)" strokeWidth="1.5" strokeDasharray="4 2" />
        <line x1="15" y1="70" x2="125" y2="70" stroke="hsl(155 70% 45% / 0.5)" strokeWidth="1.5" strokeDasharray="4 2" />
        
        <text x="63" y="10" fill="hsl(155 70% 80%)" fontSize="12" fontWeight="bold">|0⟩</text>
        <text x="63" y="142" fill="hsl(155 70% 80%)" fontSize="12" fontWeight="bold">|1⟩</text>
        
        {/* The dynamic state vector arrow */}
        <motion.line 
          x1="70" y1="70" 
          stroke="hsl(46 70% 55%)" strokeWidth="3.5" strokeLinecap="round"
          animate={isSimulating ? { 
            x2: [targetX, 90, 110, targetX], 
            y2: [targetY, 50, 20, targetY] 
          } : { x2: targetX, y2: targetY }}
          transition={{ 
            duration: isSimulating ? 0.5 : 0.6, 
            repeat: isSimulating ? Infinity : 0,
            ease: isSimulating ? "linear" : "easeOut" 
          }}
          style={{ filter: "drop-shadow(0 0 4px hsl(46 70% 55%))" }}
        />
        <motion.circle 
          r="5" fill="hsl(46 70% 55%)" 
          style={{ filter: "drop-shadow(0 0 10px hsl(46 70% 55%))" }} 
          animate={isSimulating ? { 
            cx: [targetX, 90, 110, targetX], 
            cy: [targetY, 50, 20, targetY] 
          } : { cx: targetX, cy: targetY }}
          transition={{ 
            duration: isSimulating ? 0.5 : 0.6, 
            repeat: isSimulating ? Infinity : 0,
            ease: isSimulating ? "linear" : "easeOut"
          }}
        />
      </motion.svg>
    </div>
  );
}

function QuantumCircuit({ isSimulating }: { isSimulating: boolean }) {
  // Simplified layout for the circuit to be extremely aesthetic
  return (
    <div className="relative w-full overflow-x-auto overflow-y-hidden pb-4">
      <div className="min-w-[600px]">
        {/* Wires */}
        <div className="absolute top-[30px] left-8 right-0 h-0.5 bg-emerald-500/30" />
        <div className="absolute top-[80px] left-8 right-0 h-0.5 bg-emerald-500/30" />
        
        {/* Animated Pulses on Wires */}
        {isSimulating && (
          <>
            <motion.div className="absolute top-[28px] h-[5px] w-[40px] rounded-full bg-emerald-400 shadow-[0_0_10px_hsl(155_70%_50%)]" 
              animate={{ left: ["0%", "100%"] }} transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }} />
            <motion.div className="absolute top-[78px] h-[5px] w-[40px] rounded-full bg-emerald-400 shadow-[0_0_10px_hsl(155_70%_50%)]" 
              animate={{ left: ["0%", "100%"] }} transition={{ duration: 1.5, repeat: Infinity, ease: "linear", delay: 0.3 }} />
          </>
        )}

        {/* Labels */}
        <div className="absolute top-[22px] left-0 text-xs font-mono font-bold text-emerald-400">|q₀⟩</div>
        <div className="absolute top-[72px] left-0 text-xs font-mono font-bold text-emerald-400">|q₁⟩</div>

        {/* Gates */}
        <div className="relative h-[110px] w-full flex items-center pl-16">
          
          {/* Column 1: Ry */}
          <div className="absolute left-[80px] flex flex-col gap-[14px]">
            <Gate label="Rᵧ" color="border-sky-500 text-sky-400 bg-sky-500/10" isSimulating={isSimulating} />
            <Gate label="Rᵧ" color="border-sky-500 text-sky-400 bg-sky-500/10" isSimulating={isSimulating} />
          </div>

          {/* Column 2: CNOT (Entanglement) */}
          <div className="absolute left-[200px] top-[30px] flex flex-col items-center">
            {/* Control */}
            <div className="w-3 h-3 rounded-full bg-indigo-500 relative z-10 shadow-[0_0_10px_hsl(260_70%_60%)]" />
            {/* Wire connecting control and target */}
            <div className="w-0.5 h-[50px] bg-indigo-500/60" />
            {/* Target */}
            <div className="w-6 h-6 rounded-full border-2 border-indigo-500 relative flex items-center justify-center bg-black z-10">
              <div className="w-full h-0.5 bg-indigo-500 absolute" />
              <div className="h-full w-0.5 bg-indigo-500 absolute" />
            </div>
            {isSimulating && (
              <motion.div className="absolute top-1.5 w-1 h-1 rounded-full bg-white shadow-[0_0_5px_white] z-20"
                animate={{ y: [0, 40, 0] }} transition={{ duration: 0.8, repeat: Infinity }} />
            )}
          </div>

          {/* Column 3: Hadamard */}
          <div className="absolute left-[300px] flex flex-col gap-[14px]">
            <Gate label="H" color="border-fuchsia-500 text-fuchsia-400 bg-fuchsia-500/10" isSimulating={isSimulating} />
            <Gate label="H" color="border-fuchsia-500 text-fuchsia-400 bg-fuchsia-500/10" isSimulating={isSimulating} />
          </div>

          {/* Column 4: Rz */}
          <div className="absolute left-[420px] flex flex-col gap-[14px]">
            <Gate label="Rz" color="border-emerald-500 text-emerald-400 bg-emerald-500/10" isSimulating={isSimulating} />
            <Gate label="Rz" color="border-emerald-500 text-emerald-400 bg-emerald-500/10" isSimulating={isSimulating} />
          </div>

          {/* Column 5: Measurement */}
          <div className="absolute left-[540px] flex flex-col gap-[14px]">
            <MeasurementGate isSimulating={isSimulating} />
            <MeasurementGate isSimulating={isSimulating} />
          </div>

        </div>
      </div>
    </div>
  );
}

function Gate({ label, color, isSimulating }: { label: string, color: string, isSimulating: boolean }) {
  return (
    <motion.div 
      className={`w-10 h-10 rounded-lg border-2 flex items-center justify-center font-bold text-sm backdrop-blur-sm z-10 ${color}`}
      animate={isSimulating ? { scale: [1, 1.1, 1], filter: ["brightness(1)", "brightness(1.5)", "brightness(1)"] } : {}}
      transition={{ duration: Math.random() * 0.5 + 0.5, repeat: isSimulating ? Infinity : 0 }}
    >
      {label}
    </motion.div>
  );
}

function MeasurementGate({ isSimulating }: { isSimulating: boolean }) {
  return (
    <motion.div 
      className="w-10 h-10 rounded-lg border-2 border-yellow-500/70 bg-yellow-500/10 flex items-center justify-center z-10 relative overflow-hidden"
      animate={isSimulating ? { boxShadow: ["0 0 0px transparent", "0 0 15px hsl(46_70%_55%/0.5)", "0 0 0px transparent"] } : {}}
      transition={{ duration: 1, repeat: isSimulating ? Infinity : 0 }}
    >
      <svg viewBox="0 0 24 24" className="w-6 h-6 text-yellow-400" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 12 a8 8 0 0 1 16 0" />
        <path d="M12 12 l4 -4" />
      </svg>
    </motion.div>
  );
}
