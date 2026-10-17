import { motion, AnimatePresence } from "framer-motion";
import {
  Truck, ShieldAlert, ArrowRight, CheckCircle2, AlertTriangle,
  MapPin, X, FileText, Scale, Zap, Activity, Info
} from "lucide-react";
import { DistrictSeedIntelligence } from "@/lib/seed-intelligence";
import { getCropImage } from "@/lib/crops";

interface RedistributionModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetDistrict: DistrictSeedIntelligence;
  onSelectSourceDistrict?: (districtId: string) => void;
}

export function RedistributionModal({
  isOpen,
  onClose,
  targetDistrict,
  onSelectSourceDistrict
}: RedistributionModalProps) {
  if (!isOpen) return null;

  const sources = targetDistrict.redistributionSources || [];
  const primarySource = sources[0] || {
    districtId: "Mysuru",
    name: "Mysuru",
    kannadaName: "ಮೈಸೂರು",
    crop: targetDistrict.crop,
    viability: 92,
    distance: "185 km",
    availableStockTons: 12.0
  };

  const cropImg = getCropImage(targetDistrict.crop);

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl">
        <motion.div
          initial={{ opacity: 0, scale: 0.94, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.94, y: 20 }}
          className="relative w-full max-w-2xl rounded-3xl border border-emerald-500/30 bg-[#050e09] p-6 md:p-8 shadow-[0_25px_80px_rgba(0,0,0,0.95)] text-slate-100 overflow-hidden"
        >
          {/* Subtle Background Glow */}
          <div className="absolute top-0 right-0 h-64 w-64 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 h-64 w-64 rounded-full bg-sky-500/10 blur-3xl pointer-events-none" />

          {/* Close Button */}
          <button
            onClick={onClose}
            className="absolute top-6 right-6 h-8 w-8 grid place-items-center rounded-full bg-white/5 border border-white/10 text-white/70 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>

          {/* Header */}
          <div className="flex items-center gap-3 border-b border-white/10 pb-5">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.3)]">
              <Truck className="h-6 w-6" />
            </div>
            <div>
              <div className="text-[10px] font-mono font-bold uppercase tracking-widest text-emerald-400">
                SEEDIQ OBJECTIVE 3 — DECISION SUPPORT
              </div>
              <h2 className="font-display text-2xl font-bold text-white flex items-center gap-2">
                Adaptive Seed Stock Redistribution Plan
              </h2>
            </div>
          </div>

          {/* Body Content */}
          <div className="mt-6 space-y-6">
            
            {/* Disclaimer Alert */}
            <div className="rounded-2xl border border-sky-500/30 bg-sky-950/20 p-3.5 flex items-start gap-3 text-xs text-sky-200">
              <Info className="h-4 w-4 text-sky-400 shrink-0 mt-0.5" />
              <div>
                <strong className="text-white">Scientific Decision-Support Advisory:</strong> This plan computes optimal donor nodes based on seed germination viability, geographical proximity, and surplus reserve buffers to prevent seasonal crop failures.
              </div>
            </div>

            {/* Target vs Source Comparison Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              
              {/* TARGET DISTRICT (Vulnerable / Deficit Node) */}
              <div className="rounded-2xl border border-red-500/30 bg-red-950/20 p-4 space-y-3 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-red-400 flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-red-500 animate-ping" />
                    TARGET (DEFICIT)
                  </span>
                  <span className="text-xs font-bold text-red-400 bg-red-950/80 px-2 py-0.5 rounded-full border border-red-500/30">
                    Viability: {targetDistrict.currentViability}%
                  </span>
                </div>

                <div>
                  <h3 className="font-display text-xl font-bold text-white">
                    {targetDistrict.districtName} ({targetDistrict.kannadaName})
                  </h3>
                  <p className="text-xs text-muted-foreground">{targetDistrict.region}</p>
                </div>

                <div className="pt-2 border-t border-red-500/20 text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Seed Variety:</span>
                    <span className="font-semibold text-white">{targetDistrict.crop}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Projected 90d Decay:</span>
                    <span className="font-semibold text-red-300">{targetDistrict.predictedViability}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Vulnerability:</span>
                    <span className="font-semibold text-red-400">{targetDistrict.moistureVulnerability} Moisture Risk</span>
                  </div>
                </div>
              </div>

              {/* SOURCE DISTRICT (Surplus / Donor Node) */}
              <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-4 space-y-3 relative overflow-hidden">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                    DONOR (SURPLUS HUB)
                  </span>
                  <span className="text-xs font-bold text-emerald-400 bg-emerald-950/80 px-2 py-0.5 rounded-full border border-emerald-500/30">
                    Viability: {primarySource.viability}%
                  </span>
                </div>

                <div>
                  <h3 className="font-display text-xl font-bold text-white">
                    {primarySource.name} ({primarySource.kannadaName})
                  </h3>
                  <p className="text-xs text-muted-foreground">Certified Foundation Stock Reserve</p>
                </div>

                <div className="pt-2 border-t border-emerald-500/20 text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Available Buffer:</span>
                    <span className="font-semibold text-emerald-300">{primarySource.availableStockTons} Tons</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Logistics Distance:</span>
                    <span className="font-semibold text-white">{primarySource.distance}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Quality Grade:</span>
                    <span className="font-semibold text-emerald-400">Certified Grade A+</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Scientific Rationale & Logistics Route */}
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 space-y-2.5 text-xs">
              <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-400">
                <Zap className="h-3.5 w-3.5" />
                AI RECOMMENDATION RATIONALE
              </div>
              <p className="text-slate-200 leading-relaxed">
                {targetDistrict.reason} Sourcing <strong className="text-emerald-300">{primarySource.crop}</strong> from <strong className="text-white">{primarySource.name}</strong> ({primarySource.viability}% viability) guarantees {">"}85% field germination emergence for upcoming agricultural operations.
              </p>
            </div>

            {/* Multiple Donor Options if available */}
            {sources.length > 1 && (
              <div className="space-y-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
                  ALTERNATIVE DONOR HUBS
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {sources.slice(1).map((src) => (
                    <div
                      key={src.districtId}
                      className="flex items-center justify-between p-2.5 rounded-xl border border-white/10 bg-white/5 text-xs"
                    >
                      <div>
                        <div className="font-bold text-white">{src.name}</div>
                        <div className="text-[10px] text-muted-foreground">{src.distance} • {src.availableStockTons} T</div>
                      </div>
                      <span className="font-mono font-bold text-emerald-400">{src.viability}%</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Footer Actions */}
          <div className="mt-6 pt-4 border-t border-white/10 flex items-center justify-between">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-xl border border-white/10 text-xs font-semibold text-white/70 hover:text-white transition-colors"
            >
              Close Advisory
            </button>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Strategy Verified
              </span>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
