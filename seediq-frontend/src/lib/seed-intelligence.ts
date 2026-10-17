export type RiskLevel = "CRITICAL" | "WARNING" | "MONITOR" | "STABLE";

export interface RedistributionSource {
  districtId: string;
  name: string;
  kannadaName: string;
  crop: string;
  viability: number;
  distance: string;
  availableStockTons: number;
}

export interface DistrictSeedIntelligence {
  districtId: string;
  districtName: string;
  kannadaName: string;
  region: string;
  crop: string;
  currentViability: number;
  predictedViability: number; // 90-180 day AI projection
  trend: "declining" | "stable" | "improving";
  riskLevel: RiskLevel;
  statusText: string;
  earlyWarning: string;
  recommendedAction: string;
  actionType: "redistribute" | "regenerate" | "monitor" | "stable";
  reason: string;
  alternativeAction?: string;
  storageConditionScore: number;
  moistureVulnerability: "High" | "Moderate" | "Low";
  redistributionSources?: RedistributionSource[];
}

// Configurable Early-Warning Thresholds
export const SEED_ALERT_THRESHOLDS = {
  STABLE_MIN: 80,
  MONITOR_MIN: 65,
  REGENERATION_MIN: 50,
};

export function calculateRiskLevel(viability: number, predictedViability: number): RiskLevel {
  if (viability < SEED_ALERT_THRESHOLDS.REGENERATION_MIN || predictedViability < 48) {
    return "CRITICAL";
  }
  if (viability < SEED_ALERT_THRESHOLDS.MONITOR_MIN || predictedViability < 62) {
    return "WARNING";
  }
  if (viability < SEED_ALERT_THRESHOLDS.STABLE_MIN || predictedViability < 75) {
    return "MONITOR";
  }
  return "STABLE";
}

// Centralized Single Source of Truth for Karnataka 31 Districts Seed Intelligence & Objective 3 Decision Support
export const DISTRICT_SEED_INTELLIGENCE: Record<string, DistrictSeedIntelligence> = {
  "Kolar": {
    districtId: "Kolar",
    districtName: "Kolar",
    kannadaName: "ಕೋಲಾರ",
    region: "Eastern Dry Zone",
    crop: "Tomato (Arka Rakshak)",
    currentViability: 48,
    predictedViability: 38,
    trend: "declining",
    riskLevel: "CRITICAL",
    statusText: "Critical Viability Loss — Redistribution Required",
    earlyWarning: "Tomato seed viability in regional storage has breached the safe minimum threshold (<50%). Accelerated loss predicted under high ambient heat.",
    recommendedAction: "🚚 Emergency Seed Stock Redistribution",
    actionType: "redistribute",
    reason: "Local seed stocks are failing germination viability thresholds. In-situ regeneration cycle (90 days) will miss current season sowing window.",
    alternativeAction: "🔄 Initiate rapid greenhouse seed regeneration with backup breeder lot.",
    storageConditionScore: 54,
    moistureVulnerability: "High",
    redistributionSources: [
      {
        districtId: "Mysuru",
        name: "Mysuru",
        kannadaName: "ಮೈಸೂರು",
        crop: "Tomato (Arka Rakshak)",
        viability: 91,
        distance: "185 km",
        availableStockTons: 12.5
      },
      {
        districtId: "Mandya",
        name: "Mandya",
        kannadaName: "ಮಂಡ್ಯ",
        crop: "Tomato (Arka Rakshak)",
        viability: 88,
        distance: "155 km",
        availableStockTons: 8.0
      }
    ]
  },
  "Raichur": {
    districtId: "Raichur",
    districtName: "Raichur",
    kannadaName: "ರಾಯಚೂರು",
    region: "North Eastern Dry Zone",
    crop: "Cotton & Byadagi Chilli",
    currentViability: 58,
    predictedViability: 49,
    trend: "declining",
    riskLevel: "WARNING",
    statusText: "Regeneration Recommended — Viability Declining",
    earlyWarning: "Storage temperature fluctuations in Tungabhadra basin warehouse indicate rapid moisture migration. Viability projected to drop below 50% in 45 days.",
    recommendedAction: "🔄 Initiate Controlled Seed Stock Regeneration",
    actionType: "regenerate",
    reason: "Predicted viability decline crossed the early-warning boundary (58% → 49%). Timely multiplication will restore buffer reserves before next Kharif.",
    alternativeAction: "🚚 Reserve 15 Tons seed transfer from Belagavi regional hub.",
    storageConditionScore: 62,
    moistureVulnerability: "High",
    redistributionSources: [
      {
        districtId: "Belagavi",
        name: "Belagavi",
        kannadaName: "ಬೆಳಗಾವಿ",
        crop: "Cotton (Hybrid-6)",
        viability: 89,
        distance: "280 km",
        availableStockTons: 18.0
      }
    ]
  },
  "Ballari": {
    districtId: "Ballari",
    districtName: "Ballari",
    kannadaName: "ಬಳ್ಳಾರಿ",
    region: "Eastern Dry Zone, Mining Belt",
    crop: "Maize & Sunflower",
    currentViability: 71,
    predictedViability: 64,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Environmental Alert — Close Surveillance",
    earlyWarning: "Relative humidity anomalies in storage godowns. Seed vigor remains viable but micro-climate metrics warrant bi-weekly sampling.",
    recommendedAction: "🟡 Heightened Protocol Monitoring & Dehumidification",
    actionType: "monitor",
    reason: "Moderate decline trend detected. Immediate redistribution not required if aeration protocols are adjusted.",
    alternativeAction: "🔄 Schedule batch vigor test within 30 days.",
    storageConditionScore: 74,
    moistureVulnerability: "Moderate"
  },
  "Kalaburagi": {
    districtId: "Kalaburagi",
    districtName: "Kalaburagi",
    kannadaName: "ಕಲಬುರಗಿ",
    region: "North Eastern Dry Zone, Tur Bowl",
    crop: "Pigeon Pea (Red Gram)",
    currentViability: 62,
    predictedViability: 54,
    trend: "declining",
    riskLevel: "WARNING",
    statusText: "Regeneration Recommended — Bruchid Risk",
    earlyWarning: "Post-harvest pulse beetle (bruchid) vulnerability elevated due to warm dry storage. Seed vigor index declining.",
    recommendedAction: "🔄 Seed Multiplication & Hermetic Storage Treatment",
    actionType: "regenerate",
    reason: "Red gram seed reserves require proactive seed replacement before Rabi season multiplication demand.",
    alternativeAction: "🚚 Sourcing foundation seed lots from Dharwad UAS.",
    storageConditionScore: 66,
    moistureVulnerability: "Moderate",
    redistributionSources: [
      {
        districtId: "Dharwad",
        name: "Dharwad",
        kannadaName: "ಧಾರವಾಡ",
        crop: "Pigeon Pea (Maruti ICPL-87119)",
        viability: 92,
        distance: "310 km",
        availableStockTons: 14.0
      }
    ]
  },
  "Vijayapura": {
    districtId: "Vijayapura",
    districtName: "Vijayapura",
    kannadaName: "ವಿಜಯಪುರ",
    region: "Northern Dry Zone, Deccan Basin",
    crop: "Grapes & Pomegranate",
    currentViability: 68,
    predictedViability: 62,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Moderate Seed Vigor — Active Tracking",
    earlyWarning: "Cold storage facility power reliability score lower than target. Thermal inertia preserving current viability.",
    recommendedAction: "🟡 Continuous Sensor Telemetry & Backup Chilling",
    actionType: "monitor",
    reason: "Viability metrics in monitor zone (68%). No seed deficit expected if current storage temperature (0-2°C) is maintained.",
    storageConditionScore: 77,
    moistureVulnerability: "Moderate"
  },
  "Chamarajanagar": {
    districtId: "Chamarajanagar",
    districtName: "Chamarajanagar",
    kannadaName: "ಚಾಮರಾಜನಗರ",
    region: "Southern Dry Zone, Border Foothills",
    crop: "Turmeric & Groundnut",
    currentViability: 52,
    predictedViability: 44,
    trend: "declining",
    riskLevel: "CRITICAL",
    statusText: "Critical Viability Alert — Redistribution Required",
    earlyWarning: "Rhizome moisture loss exceeding permissible threshold. Seed viability approaching non-recoverable level (<45%).",
    recommendedAction: "🚚 Seed Stock Redistribution from Mysuru",
    actionType: "redistribute",
    reason: "Seed rhizome viability degraded by localized heat stress. Sowing begins in 20 days.",
    alternativeAction: "🔄 Fast-track nursery shade-net multiplication.",
    storageConditionScore: 50,
    moistureVulnerability: "High",
    redistributionSources: [
      {
        districtId: "Mysuru",
        name: "Mysuru",
        kannadaName: "ಮೈಸೂರು",
        crop: "Turmeric (Prathibha)",
        viability: 93,
        distance: "60 km",
        availableStockTons: 9.5
      }
    ]
  },
  "Mysuru": {
    districtId: "Mysuru",
    districtName: "Mysuru",
    kannadaName: "ಮೈಸೂರು",
    region: "Southern Transition Zone, Cauvery Basin",
    crop: "Paddy & Silk/Tomato",
    currentViability: 92,
    predictedViability: 89,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Optimal Viability — Surplus Supply Hub",
    earlyWarning: "All regional storage warehouses operating under optimal climate control. No degradation detected.",
    recommendedAction: "🟢 No Immediate Action — Available as Redistribution Source",
    actionType: "stable",
    reason: "Seed viability is well above threshold (>90%). Identified as primary donor reserve for Southern Karnataka.",
    storageConditionScore: 96,
    moistureVulnerability: "Low"
  },
  "Mandya": {
    districtId: "Mandya",
    districtName: "Mandya",
    kannadaName: "ಮಂಡ್ಯ",
    region: "Southern Dry Zone, Sugar Capital",
    crop: "Sugarcane & Paddy",
    currentViability: 89,
    predictedViability: 87,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Optimal Seed Health — Stable Reserve",
    earlyWarning: "KRS canal belt storage conditions highly favorable. High germination vigour recorded across tested seed lots.",
    recommendedAction: "🟢 Maintain Standard Storage Protocols",
    actionType: "stable",
    reason: "Viability metrics at 89% with minimal predicted degradation (87% over 180 days).",
    storageConditionScore: 94,
    moistureVulnerability: "Low"
  },
  "Belagavi": {
    districtId: "Belagavi",
    districtName: "Belagavi",
    kannadaName: "ಬೆಳಗಾವಿ",
    region: "Northern Transition Zone",
    crop: "Sugarcane, Maize & Cotton",
    currentViability: 90,
    predictedViability: 88,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Robust Foundation Stock — Surplus Hub",
    earlyWarning: "Western Ghats fringe micro-climate buffering storage longevity. Seed vigour score exceptional.",
    recommendedAction: "🟢 Certified Surplus — Donor Hub for Northern Karnataka",
    actionType: "stable",
    reason: "High seed vigor (90%) and extensive warehouse capacity (18+ Tons available for redistribution).",
    storageConditionScore: 95,
    moistureVulnerability: "Low"
  },
  "Shivamogga": {
    districtId: "Shivamogga",
    districtName: "Shivamogga",
    kannadaName: "ಶಿವಮೊಗ್ಗ",
    region: "Central Malnad, Gateway to Malnad",
    crop: "Arecanut, Paddy & Ginger",
    currentViability: 86,
    predictedViability: 84,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Optimal Viability — Malnad Zone",
    earlyWarning: "High humidity managed with active dehumidification systems. Spore counts baseline.",
    recommendedAction: "🟢 Standard Preventive Maintenance",
    actionType: "stable",
    reason: "Storage conditions within optimal thresholds with 86% seed viability.",
    storageConditionScore: 91,
    moistureVulnerability: "Low"
  },
  "Dharwad": {
    districtId: "Dharwad",
    districtName: "Dharwad",
    kannadaName: "ಧಾರವಾಡ",
    region: "Northern Transition Zone, Agronomy UAS Hub",
    crop: "Soybean & Pulses",
    currentViability: 93,
    predictedViability: 91,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "UAS Research Foundation Stock — Top Tier",
    earlyWarning: "University agronomy research stores maintaining certified breeder quality across all pulse varieties.",
    recommendedAction: "🟢 Research Quality Certified — Primary Donor Node",
    actionType: "stable",
    reason: "Optimal 93% viability; acts as primary genetic donor node for North Karnataka redistribution.",
    storageConditionScore: 98,
    moistureVulnerability: "Low"
  },
  "Hassan": {
    districtId: "Hassan",
    districtName: "Hassan",
    kannadaName: "ಹಾಸನ",
    region: "Southern Transition Zone",
    crop: "Potato & Coffee",
    currentViability: 76,
    predictedViability: 70,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Monitor Potato Seed Tuber Storage",
    earlyWarning: "Early sprout inhibitor levels need renewal in cold storage units.",
    recommendedAction: "🟡 Check CIPC Treatment & Ventilation",
    actionType: "monitor",
    reason: "Potato seed tubers require strict sprout inhibition maintenance.",
    storageConditionScore: 78,
    moistureVulnerability: "Moderate"
  },
  "Bidar": {
    districtId: "Bidar",
    districtName: "Bidar",
    kannadaName: "ಬೀದರ್",
    region: "North Eastern Transition Zone",
    crop: "Black Gram & Soybean",
    currentViability: 73,
    predictedViability: 67,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Close Monitoring of Seed Moisture",
    earlyWarning: "Laterite dry terrain creating temperature spikes during midday in non-insulated godowns.",
    recommendedAction: "🟡 Enhance Aeration & Insulation",
    actionType: "monitor",
    reason: "Viability at 73%, monitoring recommended to prevent transition to regeneration status.",
    storageConditionScore: 72,
    moistureVulnerability: "Moderate"
  },
  "Yadgir": {
    districtId: "Yadgir",
    districtName: "Yadgir",
    kannadaName: "ಯಾದಗಿರಿ",
    region: "North Eastern Dry Zone",
    crop: "Red Gram & Groundnut",
    currentViability: 59,
    predictedViability: 51,
    trend: "declining",
    riskLevel: "WARNING",
    statusText: "Regeneration Recommended — Drought Impacted",
    earlyWarning: "Past season drought caused lower initial seed weight. Viability decay accelerated.",
    recommendedAction: "🔄 Fast-Track Seed Regeneration",
    actionType: "regenerate",
    reason: "Low seed endosperm density accelerating viability loss under warm warehouse conditions.",
    alternativeAction: "🚚 Seed transfer from Raichur / Dharwad.",
    storageConditionScore: 61,
    moistureVulnerability: "High",
    redistributionSources: [
      {
        districtId: "Dharwad",
        name: "Dharwad",
        kannadaName: "ಧಾರವಾಡ",
        crop: "Red Gram (ICPL-87119)",
        viability: 92,
        distance: "330 km",
        availableStockTons: 10.0
      }
    ]
  },
  "Davanagere": {
    districtId: "Davanagere",
    districtName: "Davanagere",
    kannadaName: "ದಾವಣಗೆರೆ",
    region: "Central Dry Zone, Manchester of Karnataka",
    crop: "Maize (Hybrid HQPM)",
    currentViability: 84,
    predictedViability: 81,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable Seed Reserves",
    earlyWarning: "Maize seed stock viability in certified silo storage is high and stable.",
    recommendedAction: "🟢 Routine Quality Audit",
    actionType: "stable",
    reason: "Viability well above early warning threshold (84%).",
    storageConditionScore: 89,
    moistureVulnerability: "Low"
  },
  "Chitradurga": {
    districtId: "Chitradurga",
    districtName: "Chitradurga",
    kannadaName: "ಚಿತ್ರದುರ್ಗ",
    region: "Central Dry Zone, Fort City",
    crop: "Groundnut & Onion",
    currentViability: 67,
    predictedViability: 59,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Monitor Seed Pod Moisture",
    earlyWarning: "Groundnut pod kernel moisture nearing upper threshold (9.2%).",
    recommendedAction: "🟡 Periodic Aeration & Sampling",
    actionType: "monitor",
    reason: "Preventing mold growth by maintaining strict silo moisture controls.",
    storageConditionScore: 73,
    moistureVulnerability: "Moderate"
  },
  "Tumakuru": {
    districtId: "Tumakuru",
    districtName: "Tumakuru",
    kannadaName: "ತುಮಕೂರು",
    region: "Southern Dry Zone, Coconut Belt",
    crop: "Ragi (Finger Millet) & Coconut",
    currentViability: 87,
    predictedViability: 85,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "High Seed Viability — Ragi Stock Secure",
    earlyWarning: "Finger millet demonstrates natural longevity in cool storage. No degradation observed.",
    recommendedAction: "🟢 Optimal Reserve — Long Term Preservation",
    actionType: "stable",
    reason: "Finger millet seed pericarp provides natural pest and decay resilience.",
    storageConditionScore: 92,
    moistureVulnerability: "Low"
  },
  "Chikkaballapur": {
    districtId: "Chikkaballapur",
    districtName: "Chikkaballapur",
    kannadaName: "ಚಿಕ್ಕಬಳ್ಳಾಪುರ",
    region: "Eastern Dry Zone, Nandi Foothills",
    crop: "Capsicum & Tomato",
    currentViability: 61,
    predictedViability: 52,
    trend: "declining",
    riskLevel: "WARNING",
    statusText: "Regeneration Recommended — Vegetable Seed Lot",
    earlyWarning: "Hybrid vegetable seed stock showing diminished germination vigour (61%).",
    recommendedAction: "🔄 Coordinate Local Seed Regeneration",
    actionType: "regenerate",
    reason: "Vegetable seed germination decay rate requires fresh multiplication lot.",
    alternativeAction: "🚚 Transfer certified hybrid lot from Bengaluru Agri Labs.",
    storageConditionScore: 65,
    moistureVulnerability: "High",
    redistributionSources: [
      {
        districtId: "Bengaluru Urban",
        name: "Bengaluru Urban",
        kannadaName: "ಬೆಂಗಳೂರು ನಗರ",
        crop: "Tomato (Arka Samrat)",
        viability: 95,
        distance: "65 km",
        availableStockTons: 4.5
      }
    ]
  },
  "Bengaluru Urban": {
    districtId: "Bengaluru Urban",
    districtName: "Bengaluru Urban",
    kannadaName: "ಬೆಂಗಳೂರು ನಗರ",
    region: "Eastern Dry Zone, Innovation Capital",
    crop: "High-Value Horti & Floriculture",
    currentViability: 95,
    predictedViability: 93,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "State Seed Laboratory Vault — Optimal",
    earlyWarning: "Climate-controlled biotechnology storage operating at zero thermal deviation.",
    recommendedAction: "🟢 Primary Breeder Seed Vault Active",
    actionType: "stable",
    reason: "95% viability; core redistribution seed donor facility for Karnataka state.",
    storageConditionScore: 99,
    moistureVulnerability: "Low"
  },
  "Bengaluru Rural": {
    districtId: "Bengaluru Rural",
    districtName: "Bengaluru Rural",
    kannadaName: "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ",
    region: "Eastern Dry Zone",
    crop: "Grapes & Vegetables",
    currentViability: 88,
    predictedViability: 86,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable Quality Grade A",
    earlyWarning: "Standard parameters verified.",
    recommendedAction: "🟢 Maintain Storage Protocols",
    actionType: "stable",
    reason: "Viability index optimal at 88%.",
    storageConditionScore: 93,
    moistureVulnerability: "Low"
  },
  "Ramanagara": {
    districtId: "Ramanagara",
    districtName: "Ramanagara",
    kannadaName: "ರಾಮನಗರ",
    region: "Southern Dry Zone, Silk City",
    crop: "Mulberry & Ragi",
    currentViability: 85,
    predictedViability: 82,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable Seed & Grain Viability",
    earlyWarning: "All grain storage silos verified within permissible moisture levels.",
    recommendedAction: "🟢 Routine Monitoring",
    actionType: "stable",
    reason: "Viability steady at 85%.",
    storageConditionScore: 90,
    moistureVulnerability: "Low"
  },
  "Kodagu": {
    districtId: "Kodagu",
    districtName: "Kodagu",
    kannadaName: "ಕೊಡಗು",
    region: "Southern Malnad, Coffee Land",
    crop: "Coffee & Black Pepper",
    currentViability: 86,
    predictedViability: 83,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable Quality Reserve",
    earlyWarning: "High humidity managed with airtight poly-lined seed storage.",
    recommendedAction: "🟢 Standard Aeration Protocol",
    actionType: "stable",
    reason: "Vigor remains high across shade-grown coffee seed lots.",
    storageConditionScore: 91,
    moistureVulnerability: "Low"
  },
  "Chikkamagaluru": {
    districtId: "Chikkamagaluru",
    districtName: "Chikkamagaluru",
    kannadaName: "ಚಿಕ್ಕಮಗಳೂರು",
    region: "Central Malnad, Coffee Cradle",
    crop: "Coffee & Arecanut",
    currentViability: 88,
    predictedViability: 85,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Optimal Preservation",
    earlyWarning: "Malnad weather stable, storage temperatures optimal.",
    recommendedAction: "🟢 Routine Protocol Maintenance",
    actionType: "stable",
    reason: "Viability index at 88%.",
    storageConditionScore: 92,
    moistureVulnerability: "Low"
  },
  "Uttara Kannada": {
    districtId: "Uttara Kannada",
    districtName: "Uttara Kannada",
    kannadaName: "ಉತ್ತರ ಕನ್ನಡ",
    region: "Coastal & Malnad, Forest Belt",
    crop: "Paddy & Spices",
    currentViability: 82,
    predictedViability: 79,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Coastal Storage Stable",
    earlyWarning: "Salt-air humidity managed via sealed silos.",
    recommendedAction: "🟢 Keep Hermetic Packaging",
    actionType: "stable",
    reason: "82% viability maintained.",
    storageConditionScore: 88,
    moistureVulnerability: "Low"
  },
  "Udupi": {
    districtId: "Udupi",
    districtName: "Udupi",
    kannadaName: "ಉಡುಪಿ",
    region: "Coastal Zone, Temple Coast",
    crop: "Paddy & Arecanut",
    currentViability: 83,
    predictedViability: 80,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable Coastal Silos",
    earlyWarning: "Coastal humidity baseline.",
    recommendedAction: "🟢 Routine Monitoring",
    actionType: "stable",
    reason: "Viability stable at 83%.",
    storageConditionScore: 89,
    moistureVulnerability: "Low"
  },
  "Dakshina Kannada": {
    districtId: "Dakshina Kannada",
    districtName: "Dakshina Kannada",
    kannadaName: "ದಕ್ಷಿಣ ಕನ್ನಡ",
    region: "Coastal Zone, Port Hub",
    crop: "Cashew & Arecanut",
    currentViability: 85,
    predictedViability: 82,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Optimal Coastal Seed Reserve",
    earlyWarning: "Cashew kernel storage in good status.",
    recommendedAction: "🟢 Standard Maintenance",
    actionType: "stable",
    reason: "Stable seed viability across coastal batches.",
    storageConditionScore: 90,
    moistureVulnerability: "Low"
  },
  "Bagalkot": {
    districtId: "Bagalkot",
    districtName: "Bagalkot",
    kannadaName: "ಬಾಗಲಕೋಟೆ",
    region: "Northern Dry Zone, Ghataprabha Basin",
    crop: "Sugarcane & Pomegranate",
    currentViability: 72,
    predictedViability: 66,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Monitor Warm Storage Godowns",
    earlyWarning: "Afternoon temperature rise in tin-roof warehouses.",
    recommendedAction: "🟡 Improve Ventilation & White Reflective Roof Paint",
    actionType: "monitor",
    reason: "Preventing heat accumulation in dry seed lots.",
    storageConditionScore: 75,
    moistureVulnerability: "Moderate"
  },
  "Gadag": {
    districtId: "Gadag",
    districtName: "Gadag",
    kannadaName: "ಗದಗ",
    region: "Northern Transition Zone, Wind Energy Hub",
    crop: "Cotton & Groundnut",
    currentViability: 74,
    predictedViability: 68,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Moderate Seed Vigor",
    earlyWarning: "Dry wind aeration effective but check seed pod dryness.",
    recommendedAction: "🟡 Maintain Equilibrium Moisture",
    actionType: "monitor",
    reason: "Viability at 74%, optimal for next planting if maintained.",
    storageConditionScore: 76,
    moistureVulnerability: "Moderate"
  },
  "Haveri": {
    districtId: "Haveri",
    districtName: "Haveri",
    kannadaName: "ಹಾವೇರಿ",
    region: "Kittur Karnataka, Chilli Capital",
    crop: "Byadagi Chilli & Maize",
    currentViability: 86,
    predictedViability: 83,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Chilli Seed Stock Secure",
    earlyWarning: "Byadagi cold storage operating under certified temperature control.",
    recommendedAction: "🟢 Maintain Cold Storage Regimen",
    actionType: "stable",
    reason: "Viability index high at 86%.",
    storageConditionScore: 91,
    moistureVulnerability: "Low"
  },
  "Koppal": {
    districtId: "Koppal",
    districtName: "Koppal",
    kannadaName: "ಕೊಪ್ಪಳ",
    region: "North Eastern Dry Zone, Rice Bowl of Tungabhadra",
    crop: "Paddy & Pomegranate",
    currentViability: 70,
    predictedViability: 63,
    trend: "declining",
    riskLevel: "MONITOR",
    statusText: "Monitor Paddy Seed Lots",
    earlyWarning: "Paddy seed moisture slightly elevated (13.1%).",
    recommendedAction: "🟡 Aeration & Dry Air Circulation",
    actionType: "monitor",
    reason: "Lowering moisture below 12% to prevent mold germination.",
    storageConditionScore: 74,
    moistureVulnerability: "Moderate"
  },
  "Vijayanagara": {
    districtId: "Vijayanagara",
    districtName: "Vijayanagara",
    kannadaName: "ವಿಜಯನಗರ",
    region: "Kalyana Karnataka, TB Command",
    crop: "Sugarcane & Paddy",
    currentViability: 81,
    predictedViability: 78,
    trend: "stable",
    riskLevel: "STABLE",
    statusText: "Stable River Basin Seed Health",
    earlyWarning: "Canal command zone storage running at target benchmarks.",
    recommendedAction: "🟢 Standard Monitoring",
    actionType: "stable",
    reason: "Viability steady at 81%.",
    storageConditionScore: 89,
    moistureVulnerability: "Low"
  }
};

// Helper to get all active alerts (Critical, Warning, Monitor)
export function getActiveSeedAlerts(): DistrictSeedIntelligence[] {
  const all = Object.values(DISTRICT_SEED_INTELLIGENCE);
  // Sort priority: CRITICAL (0) -> WARNING (1) -> MONITOR (2) -> STABLE (3)
  const priorityMap: Record<RiskLevel, number> = {
    "CRITICAL": 0,
    "WARNING": 1,
    "MONITOR": 2,
    "STABLE": 3
  };

  return all
    .filter(d => d.riskLevel !== "STABLE")
    .sort((a, b) => priorityMap[a.riskLevel] - priorityMap[b.riskLevel] || a.currentViability - b.currentViability);
}

// Get count of critical and warning alerts for notification badge
export function getActiveAlertsCount(): { total: number; critical: number; warning: number; monitor: number } {
  const alerts = getActiveSeedAlerts();
  const critical = alerts.filter(a => a.riskLevel === "CRITICAL").length;
  const warning = alerts.filter(a => a.riskLevel === "WARNING").length;
  const monitor = alerts.filter(a => a.riskLevel === "MONITOR").length;
  return {
    total: alerts.length,
    critical,
    warning,
    monitor
  };
}

// Helper color and icon themes for Risk Levels
export function getRiskColorTheme(risk: RiskLevel) {
  switch (risk) {
    case "CRITICAL":
      return {
        badgeBg: "bg-red-950/70 border-red-500/50 text-red-400",
        fill: "rgba(239, 68, 68, 0.40)",
        stroke: "#ef4444",
        glow: "shadow-[0_0_20px_rgba(239,68,68,0.6)]",
        text: "text-red-400",
        label: "CRITICAL",
        dot: "bg-red-500",
        iconColor: "text-red-400"
      };
    case "WARNING":
      return {
        badgeBg: "bg-amber-950/70 border-amber-500/50 text-amber-400",
        fill: "rgba(245, 158, 11, 0.35)",
        stroke: "#f59e0b",
        glow: "shadow-[0_0_20px_rgba(245,158,11,0.5)]",
        text: "text-amber-400",
        label: "WARNING",
        dot: "bg-amber-500",
        iconColor: "text-amber-400"
      };
    case "MONITOR":
      return {
        badgeBg: "bg-yellow-950/60 border-yellow-500/40 text-yellow-300",
        fill: "rgba(234, 179, 8, 0.28)",
        stroke: "#eab308",
        glow: "shadow-[0_0_15px_rgba(234,179,8,0.4)]",
        text: "text-yellow-300",
        label: "MONITOR",
        dot: "bg-yellow-400",
        iconColor: "text-yellow-400"
      };
    case "STABLE":
    default:
      return {
        badgeBg: "bg-emerald-950/60 border-emerald-500/40 text-emerald-400",
        fill: "rgba(16, 185, 129, 0.22)",
        stroke: "#10b981",
        glow: "shadow-[0_0_15px_rgba(16,185,129,0.3)]",
        text: "text-emerald-400",
        label: "STABLE",
        dot: "bg-emerald-500",
        iconColor: "text-emerald-400"
      };
  }
}
