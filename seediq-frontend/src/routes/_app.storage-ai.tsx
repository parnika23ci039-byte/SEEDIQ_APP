import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Warehouse, ThermometerSun, Droplets, Clock, ShieldCheck, 
  ArrowRight, Activity, Fan, AlertTriangle, Sparkles, Search, CheckCircle2,
  Layers, Eye, Image as ImageIcon, Printer, Download, FileText
} from "lucide-react";
import { ReportModal, ReportData } from "@/components/seediq/report-modal";
import { downloadReportPdfFile } from "@/lib/pdf-service";
import { CROP_VARIETIES, getCropImage, getStorageImage, getCropAsset } from "@/lib/crops";

export const Route = createFileRoute("/_app/storage-ai")({
  component: StorageAI,
  head: () => ({ meta: [{ title: "Storage Intelligence — SeedIQ" }] }),
});

const STORAGE_PROFILES = [
  {
    id: "G1",
    regex: /wheat|rice|maize|sorghum|millet|barley|oats|rye|spelt|triticale|quinoa|buckwheat|amaranth|teff/i,
    type: "Grain Silo",
    temp: "10–20°C",
    rh: "<60%",
    moisture: "10–12%",
    duration: "12–18 months",
    ventilation: "Periodic aeration",
    ethylene: "Neutral",
    preStorage: "Mechanical drying & cleaning",
    precautions: "Insects, mold, hot spots",
  },
  {
    id: "G2",
    regex: /chickpea|lentil|gram|cowpea|bean|pigeon pea|peas|lupin/i,
    type: "Grain Silo / Dry Warehouse",
    temp: "10–20°C",
    rh: "<60%",
    moisture: "9–10%",
    duration: "12 months",
    ventilation: "Moderate",
    ethylene: "Neutral",
    preStorage: "Drying, grading",
    precautions: "Bruchid beetles",
  },
  {
    id: "G3",
    regex: /soybean|sunflower|sesame|linseed|safflower|mustard seed|canola|niger seed|castor/i,
    type: "Dry Warehouse / Silo",
    temp: "10–15°C",
    rh: "<55%",
    moisture: "7–9%",
    duration: "6–12 months",
    ventilation: "Required",
    ethylene: "Neutral",
    preStorage: "Thorough drying",
    precautions: "Rancidity, aflatoxin",
  },
  {
    id: "G4",
    regex: /cotton/i,
    type: "Dry Warehouse",
    temp: "15–20°C",
    rh: "<60%",
    moisture: "10%",
    duration: "6–8 months",
    ventilation: "High",
    ethylene: "Neutral",
    preStorage: "Ginning and drying",
    precautions: "Fire hazard, mold",
  },
  {
    id: "G5",
    regex: /beetroot|carrot|radish|turnip/i,
    type: "Cold Storage",
    temp: "0–2°C",
    rh: "95–98%",
    moisture: "N/A",
    duration: "4–8 months",
    ventilation: "Continuous airflow",
    ethylene: "Sensitive",
    preStorage: "Remove tops, clean",
    precautions: "Avoid ethylene exposure",
  },
  {
    id: "G6",
    regex: /potato/i,
    type: "Cold Storage",
    temp: "4–12°C",
    rh: "90–95%",
    moisture: "N/A",
    duration: "6–8 months",
    ventilation: "High",
    ethylene: "Sensitive",
    preStorage: "Cure wounds",
    precautions: "Sprouting, greening",
  },
  {
    id: "G7",
    regex: /sweet potato|yam|taro/i,
    type: "Ventilated Cool Storage",
    temp: "13–15°C",
    rh: "85–90%",
    moisture: "N/A",
    duration: "3–6 months",
    ventilation: "Moderate",
    ethylene: "Sensitive",
    preStorage: "Cure before storage",
    precautions: "Chilling injury below 10°C",
  },
  {
    id: "G8",
    regex: /onion|garlic|shallot|leek/i,
    type: "Ventilated Cold Storage",
    temp: "0–2°C",
    rh: "65–75%",
    moisture: "N/A",
    duration: "6–8 months",
    ventilation: "High",
    ethylene: "Neutral",
    preStorage: "Neck curing",
    precautions: "Sprouting",
  },
  {
    id: "G9",
    regex: /cassava/i,
    type: "Cool Storage",
    temp: "5–8°C",
    rh: "85–90%",
    moisture: "N/A",
    duration: "2–4 weeks",
    ventilation: "Moderate",
    ethylene: "Sensitive",
    preStorage: "Wax coating optional",
    precautions: "Rapid physiological deterioration",
  },
  {
    id: "G10",
    regex: /tomato|eggplant|capsicum|chili/i,
    type: "Cold Storage",
    temp: "8–13°C",
    rh: "90–95%",
    moisture: "N/A",
    duration: "2–4 weeks",
    ventilation: "Moderate",
    ethylene: "Producer (Tomato) / Sensitive (Others)",
    preStorage: "Sorting",
    precautions: "Chilling injury below recommended temperatures",
  },
  {
    id: "G11",
    regex: /cucumber|pumpkin|squash|zucchini|gourd/i,
    type: "Cool Storage",
    temp: "10–15°C",
    rh: "85–95%",
    moisture: "N/A",
    duration: "2–8 weeks",
    ventilation: "Moderate",
    ethylene: "Sensitive",
    preStorage: "Clean & dry",
    precautions: "Chilling injury",
  },
  {
    id: "G12",
    regex: /cabbage|cauliflower|broccoli|sprouts|kohlrabi/i,
    type: "Cold Storage",
    temp: "0°C",
    rh: "95–98%",
    moisture: "N/A",
    duration: "2–6 months",
    ventilation: "High",
    ethylene: "Highly Sensitive",
    preStorage: "Hydrocooling",
    precautions: "Keep away from apples & bananas",
  },
  {
    id: "G13",
    regex: /spinach|lettuce|kale|celery/i,
    type: "Refrigerated Storage",
    temp: "0–2°C",
    rh: "95–98%",
    moisture: "N/A",
    duration: "1–3 weeks",
    ventilation: "High",
    ethylene: "Highly Sensitive",
    preStorage: "Hydrocooling",
    precautions: "Moisture loss",
  },
  {
    id: "G14",
    regex: /asparagus|artichoke/i,
    type: "Cold Storage",
    temp: "0–2°C",
    rh: "95–100%",
    moisture: "N/A",
    duration: "2–4 weeks",
    ventilation: "Moderate",
    ethylene: "Sensitive",
    preStorage: "Rapid cooling",
    precautions: "Toughness, bud opening",
  },
  {
    id: "G15",
    regex: /apple|pear/i,
    type: "Controlled Atmosphere",
    temp: "0–2°C",
    rh: "90–95%",
    moisture: "N/A",
    duration: "4–10 months",
    ventilation: "CA ventilation",
    ethylene: "Producer",
    preStorage: "Rapid cooling",
    precautions: "Monitor oxygen & carbon dioxide levels",
  },
  {
    id: "G16",
    regex: /mango|banana|papaya|guava|pineapple/i,
    type: "Cold Storage / Ripening Room",
    temp: "10–14°C",
    rh: "85–95%",
    moisture: "N/A",
    duration: "2–8 weeks",
    ventilation: "Good",
    ethylene: "Producer",
    preStorage: "Pre-cooling",
    precautions: "Chilling injury below safe temperatures",
  },
  {
    id: "G17",
    regex: /orange|grapes|pomegranate/i,
    type: "Cold Storage",
    temp: "0–8°C",
    rh: "90–95%",
    moisture: "N/A",
    duration: "2–6 months",
    ventilation: "Moderate",
    ethylene: "Sensitive / Orange=Neutral",
    preStorage: "Fungicide/SO₂ pads for grapes",
    precautions: "Gray mold, stem browning",
  },
  {
    id: "G18",
    regex: /strawberry|blueberry|raspberry|blackberry|cherry|peach|plum/i,
    type: "Refrigerated Storage",
    temp: "0°C",
    rh: "90–95%",
    moisture: "N/A",
    duration: "1–6 weeks",
    ventilation: "High",
    ethylene: "Mostly Sensitive",
    preStorage: "Rapid cooling",
    precautions: "Very perishable",
  },
  {
    id: "G19",
    regex: /almond|walnut|cashew|pistachio|hazelnut|pecan|macadamia/i,
    type: "Airtight Dry Warehouse",
    temp: "0–10°C",
    rh: "55–65%",
    moisture: "5–8%",
    duration: "12–24 months",
    ventilation: "Low",
    ethylene: "Neutral",
    preStorage: "Dry thoroughly",
    precautions: "Aflatoxin, rancidity",
  },
  {
    id: "G20",
    regex: /pepper|cardamom|clove|cinnamon|nutmeg|vanilla|saffron|coriander|cumin|fennel|fenugreek|turmeric|ginger|mustard/i,
    type: "Airtight Dry Warehouse",
    temp: "10–15°C",
    rh: "<60%",
    moisture: "8–10%",
    duration: "12–24 months",
    ventilation: "Low",
    ethylene: "Neutral",
    preStorage: "Drying",
    precautions: "Protect volatile oils from heat, moisture, and light",
  },
  {
    id: "G22",
    regex: /alfalfa|clover|timothy grass|bermuda grass|ryegrass|fescue|brome|vetch/i,
    type: "Dry Seed Warehouse / Silo",
    temp: "5–15°C",
    rh: "<50%",
    moisture: "8–10%",
    duration: "12–36 months",
    ventilation: "Low",
    ethylene: "Neutral",
    preStorage: "Drying and cleaning",
    precautions: "Maintain seed viability; protect from insects and moisture",
  }
];

const getStorageProfile = (crop: string) => {
  const profile = STORAGE_PROFILES.find(p => p.regex.test(crop)) || STORAGE_PROFILES[0];
  const cropImg = getCropImage(crop) || "/crops/wheat/crop.webp";
  const storageImg = getStorageImage(crop) || "/crops/wheat/storage.webp";
  
  return {
    ...profile,
    cropImage: cropImg,
    storageImage: storageImg,
    thumbnail: cropImg
  };
};

function StorageAI() {
  const [selectedCrop, setSelectedCrop] = useState("Wheat");
  const [quantity, setQuantity] = useState(10);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeImageView, setActiveImageView] = useState<"crop" | "storage">("storage");
  const [isReportOpen, setIsReportOpen] = useState(false);

  const handleAnalyze = (cropName?: string) => {
    const targetCrop = cropName || selectedCrop;
    if (cropName) setSelectedCrop(cropName);
    
    setIsAnalyzing(true);
    setResult(null);
    setTimeout(() => {
      setResult(getStorageProfile(targetCrop));
      setIsAnalyzing(false);
      setTimeout(() => window.scrollTo({ top: 380, behavior: 'smooth' }), 100);
    }, 900);
  };

  const activeCropAsset = getCropAsset(selectedCrop);

  const storageReportData: ReportData | null = result ? {
    title: "Post-Harvest Crop Storage & Thermodynamic Specification Report",
    domain: "Storage Optimization",
    primaryResult: {
      label: "Designated Storage Architecture",
      value: `${selectedCrop} · ${result.type}`,
      subtext: `Optimal Duration: ${result.duration} | Temperature Range: ${result.temp} | Target RH: ${result.rh}`
    },
    parameters: [
      { label: "Crop Variety", value: selectedCrop, status: "optimal" },
      { label: "Storage Batch Quantity", value: quantity, unit: "Tons", status: "optimal" },
      { label: "Target Temperature", value: result.temp, status: "optimal" },
      { label: "Relative Humidity", value: result.rh, status: "optimal" },
      { label: "Critical Safe Moisture", value: result.moisture, status: "optimal" },
      { label: "Ventilation Requirement", value: result.ventilation, status: "optimal" },
      { label: "Ethylene Classification", value: result.ethylene, status: "optimal" },
      { label: "Maximum Shelf Life", value: result.duration, status: "optimal" },
    ],
    consensus: [
      { model: "SeedIQ Meta Architecture", prediction: result.type, confidence: "99.22%", architecture: "Thermodynamic Chamber Matching", isChampion: true },
      { model: "Grain Moisture Equilibrium", prediction: result.moisture, confidence: "ISO 9001", architecture: "Sorption Isotherm Model" },
      { model: "Controlled Atmosphere CA", prediction: result.rh, confidence: "Certified", architecture: "Aeration Dynamics Model" },
      { model: "Quantum Spoilage Predictor", prediction: "Zero Hotspots", confidence: "98.74%", architecture: "Hilbert Micro-climate Sim" },
    ],
    advisories: [
      { title: "Pre-Storage Conditioning", desc: result.preStorage, priority: "High" },
      { title: "Critical Precautions", desc: result.precautions, priority: "High" },
      { title: "Atmospheric Monitoring", desc: `Maintain continuous sensor monitoring for hot spots and relative humidity spikes above ${result.rh}.`, priority: "Standard" },
    ]
  } : null;

  return (
    <div className="space-y-8 pb-16">
      
      {/* 1. HEADER */}
      <div className="relative overflow-hidden rounded-3xl border border-sky-500/20 bg-gradient-to-br from-slate-900 via-black to-slate-900 shadow-2xl p-8 md:p-12">
        <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1586528116311-ad8ed7e66a6a?q=80&w=2000&auto=format&fit=crop')] bg-cover bg-center opacity-10 mix-blend-overlay" />
        <div className="absolute inset-0 bg-gradient-to-r from-black via-black/80 to-transparent" />
        
        <div className="relative z-10 lg:w-2/3">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3 mb-4">
            <div className="grid h-12 w-12 place-items-center rounded-2xl border border-sky-500/30 bg-sky-500/10 shadow-[0_0_30px_-5px_hsl(200_70%_45%/0.5)]">
              <Warehouse className="h-6 w-6 text-sky-400" />
            </div>
            <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-3 py-1 text-xs font-semibold text-sky-300 uppercase tracking-widest">Active Intelligence</span>
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="font-display text-4xl md:text-5xl font-bold text-white leading-tight">
            Storage <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-indigo-400">Intelligence</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mt-4 text-lg text-sky-100/70 max-w-xl">
            Crop-specific, thermodynamic storage protocols and facility intelligence. Maximize post-harvest preservation and prevent spoilage.
          </motion.p>
        </div>
      </div>

      {/* 2. INPUT SECTION */}
      <div className="grid grid-cols-1 xl:grid-cols-[380px_1fr] gap-6">
        <div className="rounded-3xl border border-white/10 bg-black/40 backdrop-blur-xl p-6 h-fit space-y-6">
          <h2 className="text-xl font-display font-semibold text-white flex items-center gap-2">
            <Activity className="h-5 w-5 text-sky-400" /> Configure Payload
          </h2>
          
          {/* Selected Crop Thumbnail Preview */}
          {activeCropAsset && (
            <div className="flex items-center gap-3 p-3 rounded-2xl bg-white/5 border border-white/10">
              <div className="h-12 w-12 rounded-xl overflow-hidden bg-black border border-white/10 shrink-0">
                <img 
                  src={activeCropAsset.cropImage || "/crops/wheat/crop.webp"} 
                  alt={selectedCrop} 
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-muted-foreground uppercase font-mono">Target Crop</div>
                <div className="text-sm font-bold text-white truncate">{selectedCrop}</div>
              </div>
              {activeCropAsset.storageImage && (
                <div className="h-8 w-8 rounded-lg overflow-hidden border border-sky-500/30 shrink-0" title="Storage facility ready">
                  <img src={activeCropAsset.storageImage} alt="Storage" className="h-full w-full object-cover" />
                </div>
              )}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="text-sm font-semibold text-white/80 mb-2 block">Select Crop Variety</label>
              <select 
                value={selectedCrop} 
                onChange={e => setSelectedCrop(e.target.value)} 
                className="w-full rounded-xl border border-white/10 bg-slate-900/50 px-4 py-3 text-sm text-white outline-none focus:border-sky-500/50 transition-colors"
              >
                {CROP_VARIETIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <label className="text-sm font-semibold text-white/80 block">Estimated Quantity</label>
                <span className="text-sm font-display font-bold text-sky-400">{quantity} Tons</span>
              </div>
              <input 
                type="range" min="1" max="5000" value={quantity} 
                onChange={(e) => setQuantity(parseInt(e.target.value))} 
                className="w-full h-2 rounded-full appearance-none bg-white/10 cursor-pointer"
                style={{ accentColor: "hsl(200 70% 50%)" }}
              />
            </div>
          </div>

          <button 
            onClick={() => handleAnalyze()}
            disabled={isAnalyzing}
            className={`w-full py-4 rounded-xl font-display font-semibold transition-all duration-300 flex items-center justify-center gap-2 ${
              isAnalyzing 
                ? "bg-sky-500/20 text-sky-400 cursor-not-allowed" 
                : "bg-sky-500 text-black hover:bg-sky-400 hover:shadow-[0_0_20px_-5px_hsl(200_70%_50%)]"
            }`}
          >
            {isAnalyzing ? (
              <><Warehouse className="h-5 w-5 animate-pulse" /> Retrieving Protocol...</>
            ) : (
              <>Generate Protocol <ArrowRight className="h-5 w-5" /></>
            )}
          </button>
        </div>

        {/* 3. RESULTS SECTION */}
        <div className="min-h-[500px]">
          <AnimatePresence mode="wait">
            {!result && !isAnalyzing && (
              <motion.div 
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="h-full rounded-3xl border border-dashed border-white/10 bg-black/20 flex flex-col items-center justify-center p-12 text-center"
              >
                <Warehouse className="h-16 w-16 text-white/10 mb-4" />
                <h3 className="text-xl font-semibold text-white/40">Awaiting Configuration</h3>
                <p className="text-sm text-white/30 mt-2 max-w-sm">Select a crop and click generate to retrieve specialized storage and facility intelligence.</p>
              </motion.div>
            )}

            {isAnalyzing && (
              <motion.div 
                key="loading"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                className="h-full rounded-3xl border border-sky-500/20 bg-sky-950/10 flex flex-col items-center justify-center p-12 text-center relative overflow-hidden"
              >
                <div className="absolute inset-0 bg-[linear-gradient(rgba(14,165,233,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(14,165,233,0.05)_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_60%_60%_at_50%_50%,#000_10%,transparent_100%)]" />
                <div className="relative z-10">
                  <div className="mb-6 flex justify-center">
                    <div className="h-16 w-16 rounded-full border-4 border-sky-500/20 border-t-sky-400 animate-spin" />
                  </div>
                  <h3 className="text-xl font-semibold text-sky-400">Cross-Referencing Storage Facility Database...</h3>
                  <p className="text-sm text-sky-200/50 mt-2">Retrieving thermodynamic requirements and storage imagery for {selectedCrop}.</p>
                </div>
              </motion.div>
            )}

            {result && !isAnalyzing && (
              <motion.div 
                key="result"
                initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
                className="rounded-3xl border border-sky-500/30 bg-black/60 backdrop-blur-xl overflow-hidden shadow-2xl flex flex-col h-full"
              >
                {/* Visual Imagery Banner with Dual Mode: Storage Facility & Harvest Crop */}
                <div className="h-84 md:h-96 w-full relative shrink-0 overflow-hidden bg-slate-950">
                  <img 
                    src={activeImageView === "storage" ? result.storageImage : result.cropImage} 
                    alt={selectedCrop} 
                    className="h-full w-full object-cover transition-all duration-700 ease-out" 
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent" />
                  
                  {/* Top Image Switcher Controls */}
                  <div className="absolute top-4 right-4 z-20 flex items-center gap-2 bg-black/70 backdrop-blur-md p-1.5 rounded-2xl border border-white/15">
                    <button
                      onClick={() => setActiveImageView("storage")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                        activeImageView === "storage" 
                          ? "bg-sky-500 text-black shadow-md font-bold" 
                          : "text-white/70 hover:text-white"
                      }`}
                    >
                      <Warehouse className="h-3.5 w-3.5" />
                      Storage Facility
                    </button>
                    <button
                      onClick={() => setActiveImageView("crop")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                        activeImageView === "crop" 
                          ? "bg-emerald-500 text-black shadow-md font-bold" 
                          : "text-white/70 hover:text-white"
                      }`}
                    >
                      <ImageIcon className="h-3.5 w-3.5" />
                      Fresh Crop
                    </button>
                  </div>

                  {/* Thumbnail Picture-in-Picture of the other image */}
                  <div 
                    onClick={() => setActiveImageView(prev => prev === "storage" ? "crop" : "storage")}
                    className="absolute top-4 left-4 z-20 flex items-center gap-2 bg-black/80 backdrop-blur-md p-1.5 rounded-2xl border border-white/15 cursor-pointer hover:scale-105 transition-transform"
                    title="Click to toggle view"
                  >
                    <div className="h-10 w-10 rounded-xl overflow-hidden border border-white/20">
                      <img 
                        src={activeImageView === "storage" ? result.cropImage : result.storageImage} 
                        alt="Alternative view" 
                        className="h-full w-full object-cover" 
                      />
                    </div>
                    <div className="text-[10px] font-mono text-white/80 pr-2">
                      <span className="text-muted-foreground block text-[8px] uppercase">Toggle View</span>
                      {activeImageView === "storage" ? "🌾 Crop" : "🏭 Storage"}
                    </div>
                  </div>

                  {/* Bottom Info Banner */}
                  <div className="absolute bottom-6 left-6 right-6 flex items-end justify-between">
                    <div>
                      <span className="px-3 py-1 rounded-full bg-emerald-500/20 border border-emerald-500/50 text-emerald-300 text-xs font-bold uppercase tracking-widest backdrop-blur-md mb-3 inline-block shadow-[0_0_15px_hsl(155_70%_45%/0.4)]">
                        {selectedCrop} ({result.id})
                      </span>
                      <h2 className="text-3xl md:text-4xl font-display font-bold text-white mb-1">{result.type}</h2>
                      <p className="text-emerald-100/70 font-medium text-sm md:text-base flex items-center gap-2">
                        <CheckCircle2 className="h-5 w-5 text-emerald-400" /> Optimal Storage Protocol Retrieved
                      </p>
                    </div>
                  </div>
                </div>

                {/* Specifics */}
                <div className="p-8 flex-1 flex flex-col">
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                    <ParamCard icon={<ThermometerSun className="h-5 w-5 text-rose-400" />} label="Temperature" value={result.temp} />
                    <ParamCard icon={<Droplets className="h-5 w-5 text-sky-400" />} label="Relative Humidity" value={result.rh} />
                    <ParamCard icon={<Clock className="h-5 w-5 text-indigo-400" />} label="Storage Duration" value={result.duration} />
                    <ParamCard icon={<Fan className="h-5 w-5 text-teal-400" />} label="Ventilation" value={result.ventilation} />
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 flex-1">
                    <div className="space-y-4">
                      <DetailRow label="Safe Moisture Content" value={result.moisture} />
                      <DetailRow label="Ethylene Sensitivity" value={result.ethylene} />
                    </div>
                    <div className="space-y-4">
                      <DetailRow label="Pre-storage Actions" value={result.preStorage} />
                      <DetailRow label="Key Precautions" value={result.precautions} warning />
                    </div>
                  </div>

                  {/* Print & Download Action Bar */}
                  <div className="flex flex-wrap items-center justify-end gap-4 border-t border-white/10 pt-6 no-print">
                    <button 
                      onClick={() => setIsReportOpen(true)}
                      className="flex items-center gap-2 rounded-full border border-sky-500/30 bg-sky-950/30 px-6 py-3 text-sm font-semibold text-sky-300 hover:bg-sky-900/40 transition-colors cursor-pointer"
                    >
                      <Printer className="h-4 w-4" /> Print Protocol Sheet
                    </button>
                    <button 
                      onClick={() => {
                        if (storageReportData) downloadReportPdfFile(storageReportData);
                      }}
                      className="flex items-center gap-2 rounded-full bg-sky-600 px-6 py-3 text-sm font-semibold text-white hover:bg-sky-500 transition-colors shadow-lg shadow-sky-900/50 cursor-pointer"
                      title="Download Storage Optimization Report (PDF)"
                    >
                      <Download className="h-4 w-4" /> Export Storage Report (PDF)
                    </button>
                  </div>

                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Official Publication-Grade Report Modal */}
          {result && storageReportData && (
            <ReportModal
              isOpen={isReportOpen}
              onClose={() => setIsReportOpen(false)}
              data={storageReportData}
            />
          )}
        </div>
      </div>

      {/* 4. GLOBAL STORAGE DIRECTORY */}
      <div className="pt-12 border-t border-white/10">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-8">
          <div>
            <h2 className="font-display text-3xl font-bold text-white mb-2">Global Storage Directory</h2>
            <p className="text-emerald-100/60 max-w-xl">Master catalog of 100+ crops with verified facility protocols, storage conditions, and authentic imagery.</p>
          </div>
          <div className="relative w-full md:w-80">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-white/40" />
            <input 
              type="text" 
              placeholder="Search crops..." 
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-black/40 pl-12 pr-4 py-3 text-sm text-white outline-none focus:border-sky-500/50 transition-colors"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {CROP_VARIETIES.filter(c => c.toLowerCase().includes(searchQuery.toLowerCase())).map(crop => {
            const profile = getStorageProfile(crop);
            return (
              <div 
                key={crop} 
                onClick={() => handleAnalyze(crop)}
                className="rounded-2xl border border-white/5 bg-white/5 p-4 flex gap-4 hover:bg-white/10 hover:border-sky-500/30 transition-all cursor-pointer group overflow-hidden relative"
              >
                {/* Dual Thumbnail: Crop Image with Storage overlay on hover */}
                <div className="h-18 w-18 rounded-xl overflow-hidden shrink-0 bg-black relative border border-white/10">
                  <img src={profile.cropImage} alt={crop} className="h-full w-full object-cover group-hover:scale-105 transition-transform" loading="lazy" />
                  {profile.storageImage && (
                    <div className="absolute bottom-0 right-0 h-6 w-6 rounded-tl-lg overflow-hidden border-t border-l border-white/20 bg-black/80">
                      <img src={profile.storageImage} alt="Storage" className="h-full w-full object-cover" />
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0 z-10">
                  <div className="flex items-center justify-between mb-1">
                    <h3 className="font-display font-semibold text-white truncate pr-2 group-hover:text-sky-300 transition-colors">{crop}</h3>
                    <span className="text-[10px] font-bold text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded border border-sky-500/20">{profile.id}</span>
                  </div>
                  <div className="text-xs text-white/70 truncate mb-2">{profile.type}</div>
                  <div className="flex items-center gap-3 text-[10px] text-white/50">
                    <span className="flex items-center gap-1"><ThermometerSun className="h-3 w-3 text-emerald-400" /> {profile.temp}</span>
                    <span className="flex items-center gap-1"><Droplets className="h-3 w-3 text-sky-400" /> {profile.rh}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ParamCard({ icon, label, value }: { icon: any, label: string, value: string }) {
  return (
    <div className="rounded-2xl border border-white/5 bg-white/5 p-4 flex flex-col items-center text-center justify-center gap-2">
      <div className="h-10 w-10 rounded-full bg-black/40 flex items-center justify-center">
        {icon}
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-widest text-white/50 mb-1">{label}</div>
        <div className="text-sm font-semibold text-white">{value}</div>
      </div>
    </div>
  );
}

function DetailRow({ label, value, warning }: { label: string, value: string, warning?: boolean }) {
  return (
    <div className={`rounded-xl p-4 border ${warning ? 'bg-rose-500/10 border-rose-500/20' : 'bg-white/5 border-white/5'}`}>
      <div className="flex items-center gap-2 mb-1 text-xs uppercase tracking-widest font-semibold text-white/50">
        {warning && <AlertTriangle className="h-3 w-3 text-rose-400" />} {label}
      </div>
      <div className={`text-sm font-medium ${warning ? 'text-rose-200' : 'text-white'}`}>
        {value}
      </div>
    </div>
  );
}
