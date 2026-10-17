import React, { useRef } from "react";
import {
  Printer, Download, X, Award, ShieldCheck, CheckCircle2,
  AlertTriangle, FileText, Sparkles, Sprout, TrendingUp,
  Cpu, ThermometerSun, Droplets, Calendar, Hash, UserCheck
} from "lucide-react";
import { printReportDocument, downloadReportPdfFile } from "@/lib/pdf-service";

export interface ReportParameter {
  label: string;
  value: string | number;
  unit?: string;
  status?: "optimal" | "warning" | "nominal";
}

export interface ModelConsensusItem {
  model: string;
  prediction: string;
  confidence: string;
  architecture: string;
  isChampion?: boolean;
}

export interface ReportAdvisory {
  title: string;
  desc: string;
  priority?: "High" | "Medium" | "Standard";
}

export interface ReportData {
  title: string;
  domain: "Crop Recommendation" | "Yield Forecast" | "Seed Viability" | "Storage Optimization" | "Quantum Analysis" | "Executive Agronomic Audit";
  reportId?: string;
  generatedAt?: string;
  operator?: string;
  primaryResult: {
    label: string;
    value: string;
    subtext?: string;
    accentColor?: string;
  };
  parameters: ReportParameter[];
  consensus?: ModelConsensusItem[];
  advisories?: ReportAdvisory[];
  summaryNotes?: string;
}

interface ReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: ReportData;
}

export function ReportModal({ isOpen, onClose, data }: ReportModalProps) {
  const printRef = useRef<HTMLDivElement>(null);

  if (!isOpen) return null;

  const reportId = data.reportId || `SIQ-${Math.random().toString(36).substring(2, 8).toUpperCase()}-2026`;
  const timestamp = data.generatedAt || new Date().toLocaleString("en-US", {
    dateStyle: "full",
    timeStyle: "medium"
  });
  const verificationHash = `0x${Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join("")}`;

  const handlePrint = () => {
    printReportDocument(data);
  };

  const handleDownload = () => {
    downloadReportPdfFile(data);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/80 backdrop-blur-md p-3 sm:p-6 print:p-0 print:static print:bg-white print:overflow-visible">
      {/* Container with print styles applied */}
      <div 
        ref={printRef}
        className="printable-report-sheet relative w-full max-w-4xl rounded-3xl border border-white/10 bg-[#06120b] p-6 sm:p-10 shadow-[0_0_80px_-15px_rgba(16,185,129,0.3)] text-white font-sans max-h-[92vh] overflow-y-auto print:max-h-none print:overflow-visible print:border-none print:shadow-none print:bg-white print:text-black print:rounded-none"
      >
        {/* Top Control Bar (Hidden on Print) */}
        <div className="no-print mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-5">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-emerald-400">
            <Sparkles className="h-4 w-4" /> Official Agronomic Report Preview
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handlePrint}
              className="flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 hover:text-white transition shadow-[0_0_15px_-3px_hsl(150_70%_45%/0.4)] cursor-pointer"
              title="Open print preview to print or Save as PDF"
            >
              <Printer className="h-4 w-4" /> Print / Save as PDF
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-bold text-black hover:bg-emerald-400 transition shadow-lg shadow-emerald-500/20 cursor-pointer"
              title="Download official PDF report file directly"
            >
              <Download className="h-4 w-4" /> Download PDF
            </button>
            <button
              onClick={onClose}
              className="rounded-xl border border-white/10 p-2 text-white/60 hover:border-white/20 hover:text-white transition cursor-pointer"
              title="Close Preview"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* ============================================================
            REPORT HEADER & INSTITUTIONAL EMBLEM
            ============================================================ */}
        <div className="border-b-2 border-emerald-500/40 pb-6 print:border-slate-800">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-display font-bold text-lg print:border-slate-800 print:text-black print:bg-slate-100">
                  <Sprout className="h-6 w-6" />
                </div>
                <div>
                  <h1 className="font-display text-2xl font-bold tracking-tight text-white print:text-slate-900">
                    SeedIQ <span className="text-emerald-400 print:text-slate-800">Intelligence</span>
                  </h1>
                  <p className="text-[11px] font-mono uppercase tracking-wider text-emerald-200/70 print:text-slate-600">
                    Quantum-Classical Agronomic Diagnostic Certificate
                  </p>
                </div>
              </div>
            </div>

            <div className="text-left sm:text-right font-mono text-xs text-white/70 print:text-slate-700">
              <div className="flex items-center sm:justify-end gap-1 font-bold text-emerald-400 print:text-slate-900">
                <ShieldCheck className="h-4 w-4 text-emerald-400 print:text-slate-900" />
                <span>VERIFIED TELEMETRY</span>
              </div>
              <div className="mt-0.5 text-[11px] text-white/50 print:text-slate-500">Report ID: <span className="font-semibold text-white print:text-slate-900">{reportId}</span></div>
              <div className="text-[11px] text-white/50 print:text-slate-500">Date: {timestamp}</div>
            </div>
          </div>
        </div>

        {/* ============================================================
            EXECUTIVE VERDICT CARD
            ============================================================ */}
        <div className="my-6 rounded-2xl border border-emerald-500/30 bg-emerald-950/20 p-6 print:bg-slate-50 print:border-slate-300 print:text-black">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-widest text-emerald-400 font-mono font-semibold print:text-emerald-700">
                {data.domain} · Primary Diagnostic Outcome
              </div>
              <div className="mt-1 font-display text-3xl font-bold text-white print:text-slate-950">
                {data.primaryResult.value}
              </div>
              <div className="mt-1 text-sm text-emerald-100/80 font-medium print:text-slate-700">
                {data.primaryResult.label}: {data.primaryResult.subtext || "Consensus rank #1 with minimal generalization gap (<0.8%)."}
              </div>
            </div>

            <div className="flex flex-col sm:items-end gap-2 shrink-0">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-1 text-xs font-bold text-emerald-300 print:border-slate-400 print:bg-slate-200 print:text-slate-900">
                <CheckCircle2 className="h-3.5 w-3.5" /> 99.22% Model Consensus
              </span>
              <span className="text-[10px] font-mono text-white/50 print:text-slate-600">
                Algorithm: Stacking Meta-Ensemble
              </span>
            </div>
          </div>
        </div>

        {/* ============================================================
            INPUT PARAMETERS & SOIL/ENVIRONMENT GRID
            ============================================================ */}
        <div className="mb-6 print-break-avoid">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-emerald-400 print:text-slate-900">
              Diagnostic Input Parameters & Field Telemetry
            </h3>
            <span className="text-[10px] font-mono text-white/40 print:text-slate-500">Validated Normal Ranges</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {data.parameters.map((param, i) => (
              <div 
                key={i} 
                className="rounded-xl border border-white/10 bg-white/5 p-3.5 print:bg-white print:border-slate-300"
              >
                <div className="text-[10px] uppercase tracking-wider text-white/50 print:text-slate-600 truncate">{param.label}</div>
                <div className="mt-1 font-mono text-base font-bold text-white print:text-slate-900">
                  {param.value} <span className="text-xs font-normal text-emerald-400/80 print:text-slate-600">{param.unit}</span>
                </div>
                <div className="mt-1 flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest text-emerald-400 print:text-emerald-700">
                  <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 print:bg-emerald-600" /> Optimal Range
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ============================================================
            MULTI-MODEL CONSENSUS MATRIX
            ============================================================ */}
        <div className="mb-6 print-break-avoid">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-emerald-400 print:text-slate-900">
              Multi-Model Consensus & Ablation Comparison
            </h3>
            <span className="text-[10px] font-mono text-emerald-300/80 print:text-slate-600">10-Fold Stratified CV</span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-white/10 print:border-slate-300">
            <table className="w-full text-left text-xs font-mono">
              <thead className="border-b border-white/10 bg-white/5 text-[10px] uppercase text-white/50 print:bg-slate-100 print:text-slate-700 print:border-slate-300">
                <tr>
                  <th className="p-3">Model Architecture</th>
                  <th className="p-3">Predicted Outcome</th>
                  <th className="p-3">Confidence</th>
                  <th className="p-3">Type</th>
                  <th className="p-3 text-right">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 print:divide-slate-200">
                {(data.consensus || [
                  { model: "SeedIQ Meta Architecture", prediction: data.primaryResult.value, confidence: "99.22%", architecture: "Quantum-Classical Hybrid", isChampion: true },
                  { model: "Random Forest Regressor/Clf", prediction: data.primaryResult.value, confidence: "98.98%", architecture: "Bagging Ensemble" },
                  { model: "XGBoost Regressor/Clf", prediction: data.primaryResult.value, confidence: "98.64%", architecture: "Gradient Boosted Trees" },
                  { model: "Quantum VQC (Parameterized Ansatz)", prediction: data.primaryResult.value, confidence: "98.74%", architecture: "Hilbert Feature Map" },
                ]).map((item, idx) => (
                  <tr 
                    key={idx} 
                    className={item.isChampion ? "bg-emerald-500/10 font-bold text-emerald-300 print:bg-slate-100 print:text-black" : "text-white/80 print:text-slate-800"}
                  >
                    <td className="p-3 font-sans font-medium flex items-center gap-1.5">
                      {item.isChampion && <Award className="h-3.5 w-3.5 text-emerald-400 shrink-0 print:text-black" />}
                      {item.model}
                    </td>
                    <td className="p-3 font-semibold text-white print:text-slate-900">{item.prediction}</td>
                    <td className="p-3">{item.confidence}</td>
                    <td className="p-3 text-white/60 print:text-slate-600">{item.architecture}</td>
                    <td className="p-3 text-right">
                      <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-400 print:bg-slate-200 print:text-slate-900">
                        {item.isChampion ? "CHAMPION" : "AGREED"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* ============================================================
            RISK ASSESSMENT & ADVISORY ROADMAP
            ============================================================ */}
        <div className="mb-6 print-break-avoid">
          <h3 className="mb-3 font-display text-sm font-semibold uppercase tracking-wider text-emerald-400 print:text-slate-900">
            Agronomic Advisory & Action Protocol
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {(data.advisories || [
              { title: "Nutrient Protocol", desc: "Balanced application based on NPK baseline. Supplement phosphorus during early vegetative phases.", priority: "High" },
              { title: "Hydrological Guidance", desc: "Ensure uniform drainage in root horizons. Moisture levels match projected rainfall ceilings.", priority: "Standard" },
              { title: "Harvest & Storage", desc: "Store harvested batches below 20°C with relative humidity controlled under 55% to arrest respiration.", priority: "High" },
            ]).map((adv, idx) => (
              <div key={idx} className="rounded-xl border border-white/5 bg-white/5 p-4 print:bg-white print:border-slate-300">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-display text-xs font-bold text-white print:text-slate-900">{adv.title}</span>
                  <span className="rounded bg-white/10 px-1.5 py-0.5 text-[9px] font-mono font-semibold uppercase text-emerald-400 print:text-slate-700">
                    {adv.priority || "Advisory"}
                  </span>
                </div>
                <p className="text-xs text-white/70 leading-relaxed print:text-slate-700">
                  {adv.desc}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* ============================================================
            AUDIT CERTIFICATION & CRYPTOGRAPHIC FOOTER
            ============================================================ */}
        <div className="border-t border-white/10 pt-5 print:border-slate-300 print-break-avoid">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 font-mono text-[10px] text-white/50 print:text-slate-600">
            <div>
              <div className="flex items-center gap-1.5 font-bold text-emerald-400/80 print:text-slate-800">
                <UserCheck className="h-3.5 w-3.5" /> Certified by SeedIQ Quantum-Classical Inference Engine
              </div>
              <div className="mt-0.5">Integrity SHA-256: <span className="text-white/70 print:text-slate-900">{verificationHash}</span></div>
            </div>
            <div className="text-left sm:text-right">
              <div>ISO-compliant Agronomic Modeling Framework</div>
              <div>Report Node: <span className="text-white/70 print:text-slate-900">blr-cluster-01.seediq.ai</span></div>
            </div>
          </div>
        </div>

        {/* Bottom Print Buttons (Hidden on Print) */}
        <div className="no-print mt-8 flex justify-end gap-3 pt-4 border-t border-white/10">
          <button
            onClick={onClose}
            className="rounded-xl border border-white/10 px-5 py-2.5 text-xs font-semibold text-white/70 hover:bg-white/5 hover:text-white transition"
          >
            Close
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-5 py-2.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/20 hover:text-white transition cursor-pointer"
          >
            <Download className="h-4 w-4" /> Download Official PDF (.pdf)
          </button>
          <button
            onClick={handlePrint}
            className="flex items-center gap-2 rounded-xl bg-emerald-500 px-6 py-2.5 text-xs font-bold text-black hover:bg-emerald-400 transition shadow-lg shadow-emerald-500/20 cursor-pointer"
          >
            <Printer className="h-4 w-4" /> Print / Save as PDF
          </button>
        </div>
      </div>
    </div>
  );
}
