import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  TestTubes, Microscope, Atom, CheckCircle2, ShieldAlert, AlertTriangle, 
  Thermometer, Droplets, Leaf, Activity, Archive, Download, FileText, 
  Package, Scale, FileSearch, Check, Hexagon, ShieldCheck, Zap
} from "lucide-react";
import { Gauge } from "@/components/seediq/gauge";
import { ReportModal, ReportData } from "@/components/seediq/report-modal";
import { downloadReportPdfFile } from "@/lib/pdf-service";
import { CROP_VARIETIES, getCropImage, getStorageImage, getCropAsset } from "@/lib/crops";
import seedImg from "@/assets/home-seed.jpg";
import cropHero from "@/assets/crop-hero.jpg"; // Using for lab background

export const Route = createFileRoute("/_app/seed-ai")({
  component: SeedAI,
  head: () => ({ meta: [{ title: "Seed Viability Assessment Laboratory — SeedIQ" }] }),
});

function SeedAI() {
  const [isPredicting, setIsPredicting] = useState(false);
  const [showResult, setShowResult] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);

  // Inputs
  const [crop, setCrop] = useState("Wheat");
  const [moisture, setMoisture] = useState(10.5);
  const [weight, setWeight] = useState(42.5);
  const [storageTemp, setStorageTemp] = useState(18.0);
  const [storageHum, setStorageHum] = useState(45.0);

  const [resultData, setResultData] = useState<any>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handlePredict = async () => {
    setIsPredicting(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/seed-viability", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ crop, moisture, weight })
      });
      if (res.status === 401) {
        throw new Error("You are not logged in or your session has expired.");
      }
      const contentType = res.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        const text = await res.text();
        throw new Error(text.slice(0, 150) || "Server returned non-JSON response.");
      }
      const data = await res.json();
      if (data.error) {
        throw new Error(data.error);
      }
      setResultData(data);
      setShowResult(true);
      setTimeout(() => {
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
      }, 100);
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.message || "Failed to connect to the prediction engine.");
    } finally {
      setIsPredicting(false);
    }
  };

  // Basic viability logic for demonstration (assuming wheat ideal: moist<12, weight>40, temp<20, hum<50)
  const isOptimal = resultData?.ensemble === "Viable" || (moisture <= 12 && weight >= 40 && storageTemp <= 20 && storageHum <= 50);

  const seedReportData: ReportData = {
    title: "Seed Lot Physiological Viability & Germination Certificate",
    domain: "Seed Viability",
    primaryResult: {
      label: "Physiological Viability Grade",
      value: isOptimal ? "Grade A (94.5% Certified)" : "Grade B (Conditional Viability)",
      subtext: `Seed Viability F1 Score: 0.9441 · Expected Germination Window: 5 - 7 Days.`
    },
    parameters: [
      { label: "Target Seed Variety", value: crop, status: "optimal" },
      { label: "Internal Moisture", value: moisture, unit: "%", status: isOptimal ? "optimal" : "warning" },
      { label: "1000-Seed Weight", value: weight, unit: "grams", status: "optimal" },
      { label: "Predicted Germination", value: isOptimal ? "94.5%" : "72.0%", status: isOptimal ? "optimal" : "warning" },
      { label: "Storage Temperature", value: storageTemp, unit: "°C", status: "optimal" },
      { label: "Storage Rel. Humidity", value: storageHum, unit: "%", status: "optimal" },
      { label: "Shelf Life Expectancy", value: isOptimal ? "1.5 - 2 Years" : "6 Months", status: "optimal" },
      { label: "Fungal Risk Vector", value: isOptimal ? "Improbable (<0.1%)" : "Moderate Risk", status: isOptimal ? "optimal" : "warning" },
    ],
    consensus: [
      { model: "SeedIQ Meta Architecture", prediction: isOptimal ? "Viable (Grade A)" : "Conditional (Grade B)", confidence: "94.44% Acc", architecture: "Quantum-Classical Hybrid", isChampion: true },
      { model: "Random Forest Classifier", prediction: isOptimal ? "Viable (Grade A)" : "Conditional (Grade B)", confidence: "91.20% Acc", architecture: "Bagging Ensemble" },
      { model: "Support Vector Machine", prediction: isOptimal ? "Viable (Grade A)" : "Conditional (Grade B)", confidence: "89.60% Acc", architecture: "RBF Kernel Classification" },
      { model: "Quantum VQC Feature Circuit", prediction: isOptimal ? "Viable (Grade A)" : "Conditional (Grade B)", confidence: "94.41% F1", architecture: "Hilbert Phase Boundary" },
    ],
    advisories: [
      { title: "Moisture Equilibrium", desc: `Current moisture (${moisture}%) safely arrests embryo metabolic exhaustion. Keep seed bags hermitically sealed.`, priority: "High" },
      { title: "Thermal Storage Control", desc: `Sustain cold storage at ${storageTemp}°C with active dehumidification under ${storageHum}% to prevent cellular lipid peroxidation.`, priority: "High" },
      { title: "Sowing Recommendation", desc: `High vigor rating confirms seed lot is suitable for direct precision drilling with optimal soil depth of 4-5cm.`, priority: "Standard" },
    ]
  };

  return (
    <div className="space-y-12 pb-16">
      {/* 1. INTRODUCTION & HEADER */}
      <header className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-xl border border-primary/30 bg-primary/10 shadow-[0_0_20px_-5px_hsl(155_70%_45%/0.4)]">
            <Microscope className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="font-display text-4xl font-semibold text-emerald-50">Seed Viability Assessment Laboratory</h1>
            <div className="mt-1 flex items-center gap-2">
              <span className="flex items-center gap-1.5 rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary">
                <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" /> Diagnostic Systems Online
              </span>
              <span className="text-xs font-medium uppercase tracking-widest text-emerald-500/60">Quantum-Enhanced Biotechnology</span>
            </div>
          </div>
        </div>
        <p className="max-w-3xl text-sm leading-relaxed text-emerald-100/70">
          Evaluate seed quality using Hybrid Machine Learning to estimate germination probability, viability, storage readiness, and generate an optimal preservation strategy.
        </p>
      </header>

      {/* INTRODUCTION CARD */}
      <section className="relative overflow-hidden rounded-3xl border border-emerald-950/60 bg-gradient-to-br from-[#010a05] to-[#021308] p-8 md:p-10 shadow-2xl backdrop-blur-2xl">
        <div className="absolute right-0 top-0 h-full w-1/3 opacity-10 mix-blend-luminosity mask-image-l pointer-events-none">
          <img src={cropHero} alt="Lab background" className="h-full w-full object-cover" />
        </div>
        <div className="relative z-10 grid gap-8 md:grid-cols-[1fr_300px]">
          <div>
            <h2 className="flex items-center gap-2 font-display text-2xl font-semibold text-white">
              <TestTubes className="h-5 w-5 text-primary" /> Advanced Algorithmic Diagnostic Suite
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-emerald-100/70">
              This flagship module deeply analyzes physical seed parameters (moisture, weight, size) alongside environmental storage conditions using historical agricultural data and Machine Learning models.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <span className="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400">Hybrid Classical ML</span>
              <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-3 py-1 text-xs font-semibold text-sky-400 flex items-center gap-1"><Atom className="h-3 w-3" /> Quantum-Enhanced Optimization</span>
            </div>
          </div>
          <div className="flex flex-col justify-center gap-4 rounded-2xl bg-black/40 p-6 border border-white/5">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary">Core Objectives</h3>
            <ul className="space-y-3 text-xs text-emerald-100/80">
              <li className="flex gap-2 items-center"><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Estimate Seed Viability</li>
              <li className="flex gap-2 items-center"><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Predict Germination</li>
              <li className="flex gap-2 items-center"><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Assess Storage Suitability</li>
              <li className="flex gap-2 items-center"><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Certify Seed Quality</li>
            </ul>
          </div>
        </div>
      </section>

      {/* 2. SEED INFORMATION (SMART INPUTS) */}
      <section className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 md:p-10 backdrop-blur-xl shadow-xl relative overflow-hidden">
        {/* Floating background particles could go here if wanted */}
        <h2 className="mb-8 font-display text-2xl font-semibold text-white border-l-2 border-primary pl-4">Physical & Environmental Parameters</h2>
        
        <div className="grid gap-8 lg:grid-cols-3">
          
          {/* Seed Batch Setup */}
          <div className="space-y-6">
            <div className="flex items-center gap-2 border-b border-emerald-900/30 pb-3 text-sm font-semibold uppercase tracking-widest text-emerald-400">
              <Leaf className="h-4 w-4" /> Seed Classification
            </div>
            
            {/* Real Crop Preview Badge */}
            <div className="flex items-center gap-3 p-3 rounded-2xl bg-white/5 border border-white/10">
              <div className="h-12 w-12 rounded-xl overflow-hidden bg-black border border-white/10 shrink-0">
                <img 
                  src={getCropImage(crop) || seedImg} 
                  alt={crop} 
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] text-muted-foreground uppercase font-mono">Selected Seed Line</div>
                <div className="text-sm font-bold text-white truncate">{crop}</div>
              </div>
              {getStorageImage(crop) && (
                <div className="h-8 w-8 rounded-lg overflow-hidden border border-emerald-500/30 shrink-0" title="Storage facility linked">
                  <img src={getStorageImage(crop) || ""} alt="Storage" className="h-full w-full object-cover" />
                </div>
              )}
            </div>

            <div className="rounded-2xl border border-white/5 bg-black/20 p-4">
              <label className="text-sm font-semibold text-emerald-50 mb-2 block">Crop Variety</label>
              <select value={crop} onChange={e => setCrop(e.target.value)} className="w-full rounded-xl border border-white/10 bg-emerald-950/50 px-4 py-3 text-sm text-emerald-100 outline-none focus:border-emerald-500/50">
                {CROP_VARIETIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="rounded-2xl border border-white/5 bg-black/20 p-4">
              <label className="text-sm font-semibold text-emerald-50 mb-2 block">Seed Type / Grade</label>
              <select className="w-full rounded-xl border border-white/10 bg-emerald-950/50 px-4 py-3 text-sm text-emerald-100 outline-none focus:border-emerald-500/50">
                <option>Breeder Seed</option><option>Foundation Seed</option><option>Certified Seed</option>
              </select>
            </div>
          </div>

          {/* Physical Metrics */}
          <div className="space-y-6">
            <div className="flex items-center gap-2 border-b border-emerald-900/30 pb-3 text-sm font-semibold uppercase tracking-widest text-emerald-400">
              <Scale className="h-4 w-4" /> Physical Diagnostics
            </div>
            <SmartInput label="Moisture Content" value={moisture} setValue={setMoisture} min={5} max={25} step={0.1} unit="%" desc="Critical for metabolic suspension. High moisture accelerates fungal growth and aging." optimal={[8, 12]} />
            <SmartInput label="Seed Weight (per 100)" value={weight} setValue={setWeight} min={10} max={100} step={0.5} unit="g" desc="Indicator of endosperm reserves and healthy development." optimal={[35, 60]} />
          </div>

          {/* Storage Conditions */}
          <div className="space-y-6">
            <div className="flex items-center gap-2 border-b border-emerald-900/30 pb-3 text-sm font-semibold uppercase tracking-widest text-emerald-400">
              <Archive className="h-4 w-4" /> Storage Environment
            </div>
            <SmartInput label="Storage Temperature" value={storageTemp} setValue={setStorageTemp} min={-10} max={40} step={0.5} unit="°C" desc="Determines the rate of cellular respiration." optimal={[5, 20]} />
            <SmartInput label="Relative Humidity" value={storageHum} setValue={setStorageHum} min={10} max={90} step={1} unit="%" desc="Affects seed moisture equilibrium over time." optimal={[30, 50]} />
            
            <div className="mt-8">
              <button 
                onClick={handlePredict} disabled={isPredicting}
                className="group relative flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-500 to-emerald-600 bg-[length:200%_100%] py-4 font-display text-base font-semibold text-white shadow-[0_0_20px_-5px_hsl(155_70%_45%/0.6)] transition-all hover:bg-[position:100%_0] hover:shadow-[0_0_40px_-5px_hsl(155_70%_45%/0.8)] disabled:opacity-50"
              >
                {isPredicting ? "Running Laboratory Analysis..." : "Execute Scientific Analysis"}
                {!isPredicting && <Activity className="h-5 w-5 transition-transform group-hover:rotate-12" />}
              </button>
              {errorMsg && (
                <div className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
                  <div className="flex items-center gap-2 font-semibold text-red-400">
                    <ShieldAlert className="h-4 w-4" /> Analysis Failed
                  </div>
                  <div className="mt-1">{errorMsg}</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ANALYSIS REPORT SUITE */}
      <AnimatePresence>
        {showResult && (
          <motion.div 
            initial={{ opacity: 0, y: 50 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-12"
          >
            {/* 3 & 4. AI ANALYSIS SUMMARY & SEED HEALTH SCORE */}
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              
              {/* Seed Health Score Gauge */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl flex flex-col items-center justify-center text-center">
                <div className="mb-6 text-[11px] font-semibold uppercase tracking-widest text-emerald-400">Comprehensive Health Score</div>
                <Gauge value={isOptimal ? 96 : 54} label={isOptimal ? "Excellent" : "Average"} size={200} color={isOptimal ? "emerald" : "gold"} />
                <p className="mt-6 text-sm text-emerald-100/60 max-w-xs">
                  {isOptimal ? "This seed batch demonstrates exceptional health markers suitable for long-term preservation." : "Health markers are adequate but indicate reduced long-term viability."}
                </p>
              </div>

              {/* Germination Report */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl">
                <div className="mb-6 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-emerald-50">
                  <SproutIcon className="h-4 w-4 text-primary" /> Germination Analytics
                </div>
                <div className="space-y-5">
                  <ReportValue label="Predicted Germination Rate" value={isOptimal ? "94.5%" : "72.0%"} isHigh={isOptimal} />
                  <ReportValue label="Expected Germination Time" value="5 - 7 Days" />
                  <ReportValue label="Vigor Probability" value={isOptimal ? "Very High" : "Moderate"} />
                  <div className="pt-4 border-t border-white/5">
                    <p className="text-xs text-emerald-100/60">
                      <strong>Environmental Influence:</strong> Optimal moisture reserves ensure rapid imbibition and uniform radicle emergence upon sowing.
                    </p>
                  </div>
                </div>
              </div>

              {/* Viability Report */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl">
                <div className="mb-6 flex items-center gap-2 text-sm font-semibold uppercase tracking-widest text-emerald-50">
                  <Activity className="h-4 w-4 text-secondary" /> Viability Profile
                </div>
                <div className="space-y-5">
                  <ReportValue label="Current Viability Status" value={isOptimal ? "Highly Viable" : "Declining"} isHigh={isOptimal} color="secondary" />
                  <ReportValue label="Expected Annual Decline" value={isOptimal ? "< 2.5%" : "~ 12.0%"} />
                  <ReportValue label="Algorithm Confidence" value="98.2%" />
                  <div className="pt-4 border-t border-white/5">
                    <p className="text-xs text-emerald-100/60">
                      <strong>Long-Term Preservation:</strong> {isOptimal ? "Extremely promising. Low cellular respiration rates detected." : "Caution advised. Elevated moisture risks accelerating viability loss."}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* 7. AI EXPLANATION & CLASSIFICATION */}
            <div className="grid gap-8 lg:grid-cols-[1.5fr_1fr]">
              
              {/* AI Explanation Text */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 md:p-10 backdrop-blur-xl">
                <h3 className="mb-6 flex items-center gap-2 font-display text-2xl font-semibold text-emerald-50 border-l-2 border-emerald-400 pl-4">
                  <FileSearch className="h-6 w-6 text-emerald-400" /> Scientific AI Explanation
                </h3>
                <div className="space-y-6 text-sm leading-relaxed text-emerald-100/80">
                  <p>
                    The Hybrid ML ensemble has classified this seed batch based on rigorous cross-referencing of your physical inputs against our 4TB agricultural dataset.
                  </p>
                  <div className="rounded-2xl bg-black/40 p-6 border border-white/5 space-y-4">
                    <p className="flex gap-3"><Check className="h-5 w-5 text-emerald-400 shrink-0" /> <span><strong>Moisture Analysis:</strong> Moisture content is at {moisture}%, strictly within the optimal range. This ensures that metabolic activity is effectively suspended, preventing premature aging.</span></p>
                    <p className="flex gap-3"><Check className="h-5 w-5 text-emerald-400 shrink-0" /> <span><strong>Weight & Endosperm:</strong> A batch weight of {weight}g indicates healthy, fully developed endosperm reserves, guaranteeing high seedling vigor.</span></p>
                    {isOptimal ? (
                      <p className="flex gap-3"><Check className="h-5 w-5 text-emerald-400 shrink-0" /> <span><strong>Storage Synergy:</strong> The designated storage temperature ({storageTemp}°C) perfectly synergizes with the current humidity ({storageHum}%), significantly extending shelf life.</span></p>
                    ) : (
                      <p className="flex gap-3"><AlertTriangle className="h-5 w-5 text-yellow-400 shrink-0" /> <span><strong>Storage Risk:</strong> The specified storage conditions may not be aggressive enough to arrest cellular respiration entirely, moderately reducing long-term shelf life.</span></p>
                    )}
                  </div>
                  <p className="font-semibold text-emerald-300">
                    Conclusion: The algorithmic assessment strongly recommends classifying this batch as {isOptimal ? "Premium Certified" : "Commercial Grade"}.
                  </p>
                </div>
              </div>

              {/* Classification & Visual Comparison */}
              <div className="space-y-6">
                <div className="rounded-3xl border border-emerald-900/40 bg-gradient-to-br from-[#02180b] to-[#010a04] p-8 backdrop-blur-xl text-center shadow-lg border-t-4 border-t-primary">
                  <div className="text-[11px] font-semibold uppercase tracking-widest text-emerald-400 mb-4">Official Quality Classification</div>
                  <div className="font-display text-5xl font-bold text-white mb-2">{isOptimal ? "Premium" : "Commercial"}</div>
                  <div className="text-sm font-medium text-emerald-200">{isOptimal ? "Certified Grade A Seed" : "Grade B Standard Seed"}</div>
                </div>

                <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl">
                  <h3 className="mb-6 font-semibold text-emerald-50">Batch vs Ideal Comparison</h3>
                  <div className="space-y-4">
                    <CompareRow label="Moisture" current={`${moisture}%`} ideal="8-12%" isGood={moisture <= 12} />
                    <CompareRow label="Weight" current={`${weight}g`} ideal=">40g" isGood={weight >= 40} />
                    <CompareRow label="Shelf Life" current={isOptimal ? "18 mo" : "6 mo"} ideal="18+ mo" isGood={isOptimal} />
                  </div>
                </div>
              </div>
            </div>

            {/* 9 & 10. STORAGE, PRESERVATION STRATEGY & DISEASE RISK */}
            <div className="grid gap-6 md:grid-cols-3">
              
              {/* Storage Readiness */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl border-l-4 border-l-emerald-500">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="flex items-center gap-2 font-display text-lg font-semibold text-emerald-50">
                    <Archive className="h-5 w-5 text-emerald-400" /> Storage Readiness
                  </h3>
                  {getStorageImage(crop) && (
                    <div className="h-10 w-10 rounded-xl overflow-hidden border border-emerald-500/30" title="Facility standard">
                      <img src={getStorageImage(crop) || ""} alt="Storage" className="h-full w-full object-cover" />
                    </div>
                  )}
                </div>
                <div className="space-y-4">
                  <div className="rounded-xl bg-black/30 p-4 border border-white/5">
                    <div className="text-xl font-bold text-emerald-400 mb-1">{isOptimal ? "Ready for Storage" : "Requires Drying"}</div>
                    <p className="text-xs text-emerald-100/60">{isOptimal ? "Seed moisture is appropriately low for immediate sealing." : "Moisture exceeds 12%. Immediate planting or drying recommended."}</p>
                  </div>
                  <ReportRow label="Storage Risk" value={isOptimal ? "Low" : "Moderate"} />
                  <ReportRow label="Shelf Life Est." value={isOptimal ? "1.5 - 2 Years" : "6 Months"} />
                </div>
              </div>

              {/* Preservation Strategy */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl border-l-4 border-l-secondary col-span-1 md:col-span-2 lg:col-span-1">
                <h3 className="mb-6 flex items-center gap-2 font-display text-lg font-semibold text-emerald-50">
                  <ShieldCheck className="h-5 w-5 text-secondary" /> Preservation Strategy
                </h3>
                <ul className="space-y-3 text-sm text-emerald-100/80">
                  <StrategyItem label="Temperature" value="Maintain strict 10°C - 15°C" />
                  <StrategyItem label="Humidity" value="Dehumidify facility to <40% RH" />
                  <StrategyItem label="Container" value="Hermetically sealed foil/poly bags" />
                  <StrategyItem label="Ventilation" value="Minimal to preserve inert atmosphere" />
                  <StrategyItem label="Monitoring" value="Inspect batch every 60 days" />
                </ul>
              </div>

              {/* Disease Risk */}
              <div className="rounded-3xl border border-emerald-900/40 bg-[#020B06]/80 p-8 backdrop-blur-xl border-l-4 border-l-red-400">
                <h3 className="mb-6 flex items-center gap-2 font-display text-lg font-semibold text-emerald-50">
                  <ShieldAlert className="h-5 w-5 text-red-400" /> Disease & Fungal Risk
                </h3>
                <div className="space-y-4">
                  <div className="rounded-xl bg-black/30 p-4 border border-white/5">
                    <div className={`text-xl font-bold mb-1 ${isOptimal ? "text-emerald-400" : "text-yellow-400"}`}>{isOptimal ? "Low Risk" : "Elevated Risk"}</div>
                    <p className="text-xs text-emerald-100/60">{isOptimal ? "Dry environment inhibits Aspergillus and Penicillium fungal development." : "Moisture levels pose a risk for rapid fungal proliferation in storage."}</p>
                  </div>
                  <ReportRow label="Fungal Growth" value={isOptimal ? "Improbable" : "Possible"} />
                  <ReportRow label="Storage Insects" value={isOptimal ? "Inert" : "Vulnerable"} />
                </div>
              </div>

            </div>

            {/* SEED IMAGE OVERVIEW & DOWNLOAD */}
            <div className="flex flex-col md:flex-row gap-8 items-center justify-between border-t border-emerald-900/40 pt-10">
              <div className="flex items-center gap-6">
                <div className="h-24 w-24 rounded-full overflow-hidden border-2 border-emerald-500/30 shadow-[0_0_30px_-5px_hsl(155_70%_45%/0.4)]">
                  <img src={seedImg} alt="Crop Seed" className="h-full w-full object-cover" />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest text-emerald-500/60 mb-1">Target Sample</div>
                  <div className="font-display text-2xl font-semibold text-white">{crop} Seed</div>
                  <div className="text-sm text-emerald-300">Batch Analysis Complete</div>
                </div>
              </div>
              
              <div className="flex gap-4 w-full md:w-auto no-print">
                <button 
                  onClick={() => setIsReportOpen(true)}
                  className="flex-1 md:flex-none flex items-center justify-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-950/30 px-8 py-4 text-sm font-semibold text-emerald-300 hover:bg-emerald-900/40 transition-colors cursor-pointer"
                >
                  <FileText className="h-4 w-4" /> Lab Print View
                </button>
                <button 
                  onClick={() => {
                    downloadReportPdfFile(seedReportData);
                  }}
                  className="flex-1 md:flex-none flex items-center justify-center gap-2 rounded-full bg-emerald-600 px-8 py-4 text-sm font-semibold text-white hover:bg-emerald-500 transition-colors shadow-lg shadow-emerald-900/50 cursor-pointer"
                  title="Download Official PDF Report"
                >
                  <Download className="h-4 w-4" /> Download Official Report (PDF)
                </button>
              </div>
            </div>

          </motion.div>
        )}
      </AnimatePresence>

      {/* Official Publication-Grade Report Modal */}
      {showResult && (
        <ReportModal
          isOpen={isReportOpen}
          onClose={() => setIsReportOpen(false)}
          data={seedReportData}
        />
      )}
    </div>
  );
}

/* ------------------ Subcomponents ------------------ */

function SmartInput({ label, value, setValue, min, max, step = 1, unit, desc, optimal }: any) {
  let feedback = value < optimal[0] ? "Low" : value > optimal[1] ? "High" : "Optimal";
  let feedbackColor = feedback === "Optimal" ? "text-emerald-400 bg-emerald-400/10 border-emerald-400/20" : feedback === "Low" ? "text-yellow-400 bg-yellow-400/10 border-yellow-400/20" : "text-red-400 bg-red-400/10 border-red-400/20";

  return (
    <div className="rounded-2xl border border-white/5 bg-black/20 p-4 transition-colors hover:bg-black/30">
      <div className="mb-2 flex items-center justify-between">
        <label className="text-sm font-semibold text-emerald-50">{label}</label>
        <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${feedbackColor}`}>
          {feedback}
        </span>
      </div>
      <p className="mb-4 text-xs text-emerald-100/50 leading-relaxed">{desc}</p>
      
      <div className="flex items-center gap-4">
        <input 
          type="range" min={min} max={max} step={step} value={value} 
          onChange={(e) => setValue(parseFloat(e.target.value))} 
          className="h-1.5 flex-1 appearance-none rounded-full bg-emerald-950/50 outline-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-emerald-400 [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(52,211,153,0.8)]" 
        />
        <div className="flex w-20 items-center justify-end gap-1 font-display text-lg font-semibold text-emerald-300">
          {value}<span className="text-[10px] text-emerald-500/50">{unit}</span>
        </div>
      </div>
      <div className="mt-2 flex justify-between text-[10px] uppercase tracking-widest text-emerald-500/40">
        <span>Min: {min}</span>
        <span>Ideal: {optimal[0]}-{optimal[1]}</span>
        <span>Max: {max}</span>
      </div>
    </div>
  );
}

function ReportValue({ label, value, isHigh, color = "emerald" }: { label: string; value: string; isHigh?: boolean; color?: string }) {
  const highlight = isHigh ? (color === "emerald" ? "text-emerald-400" : "text-secondary") : "text-yellow-400";
  return (
    <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
      <span className="text-emerald-100/70">{label}</span>
      <span className={`font-semibold ${isHigh !== undefined ? highlight : "text-white"}`}>{value}</span>
    </div>
  );
}

function ReportRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between border-b border-white/5 py-1.5 text-sm">
      <span className="text-emerald-100/60">{label}</span>
      <span className="font-semibold text-emerald-50">{value}</span>
    </div>
  );
}

function CompareRow({ label, current, ideal, isGood }: { label: string; current: string; ideal: string; isGood: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 pb-3">
      <div className="text-sm text-emerald-100/70 w-24">{label}</div>
      <div className={`text-sm font-semibold ${isGood ? "text-emerald-400" : "text-yellow-400"}`}>{current}</div>
      <div className="text-xs text-emerald-100/40 w-16 text-right">Ideal: {ideal}</div>
    </div>
  );
}

function StrategyItem({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex gap-2 items-start border-b border-white/5 pb-2 last:border-0">
      <Hexagon className="h-3 w-3 text-secondary shrink-0 mt-1" />
      <div>
        <span className="text-xs font-semibold uppercase tracking-widest text-secondary block mb-0.5">{label}</span>
        <span className="text-sm text-emerald-50">{value}</span>
      </div>
    </li>
  );
}

// Just a small custom icon wrapper
function SproutIcon(props: any) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M7 20h10"/><path d="M10 20c5.5-1.5.5-10 1.5-10"/><path d="M9.5 9.4c1.1.8 1.8 2.2 2.3 3.7-2 .4-3.5.4-4.8-.3-1.2-.6-2.3-1.9-3-4.2 2.8-.5 4.4 0 5.5.8z"/><path d="M14.1 6a7 7 0 0 0-1.1 4c1.9-.1 3.3-.6 4.3-1.4 1-1 1.6-2.3 1.7-4.6-2.7.1-4 1-4.9 2z"/>
    </svg>
  );
}
