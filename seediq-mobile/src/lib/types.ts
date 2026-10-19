// Shared TypeScript types mirroring the Flask backend responses.

export type UserRole = "Admin" | "Researcher" | "Farmer" | "Guest";

export interface User {
  id: string | number;
  username: string;
  email: string;
  name: string;
  display_name?: string;
  role: UserRole;
  isGuest?: boolean;
  provider?: string;
  /** E.164 without the leading '+'. Set for phone-authenticated accounts. */
  phone?: string;
}

// ---------------------------------------------------------------------------
// Crop recommendation (/api/crop-recommendation)
// ---------------------------------------------------------------------------
export interface CropPredictionResult {
  classical: string;
  quantum: string;
  ensemble: string;
  error?: string;
}

export interface SoilNutrientAdvice {
  status: string;
  advice: string;
}

export interface SoilAnalysis {
  nitrogen: SoilNutrientAdvice;
  phosphorus: SoilNutrientAdvice;
  potassium: SoilNutrientAdvice;
  ph: SoilNutrientAdvice;
}

export interface GrowthPlanStep {
  week: string;
  stage: string;
  action: string;
}

export interface DiseaseAdvisory {
  [key: string]: unknown;
}

export interface CropRecommendationResponse {
  result: CropPredictionResult;
  soil_analysis: SoilAnalysis;
  growth_plan: GrowthPlanStep[];
  /** "knowledge_base/growth_planner.json" or "generic-fallback". */
  growth_plan_source?: string | null;
  disease_advisory: DiseaseAdvisory[];
}

// ---------------------------------------------------------------------------
// Yield prediction (/api/yield-prediction)
// ---------------------------------------------------------------------------
export interface YieldResult {
  classical: number;
  /** null when the quantum regressor could not run on the server. */
  quantum: number | null;
  ensemble: number;
  quantum_available?: boolean;
  error?: string;
}

export interface MarketAnalysis {
  price_per_tonne?: string | null;
  gross_revenue?: string | null;
  /** null when the knowledge base has no cost-of-cultivation figure. */
  total_cost?: string | null;
  /** null when cost data is unavailable — profit is never estimated from it. */
  net_profit?: string | null;
  profit_sign?: number | null;
  demand?: string | null;
  trend?: string | null;
  /** e.g. "knowledge_base/market_analysis.json#Rice", or null when absent. */
  data_source?: string | null;
  /** Populated whenever price/profit could not be sourced. */
  note?: string | null;
}

export interface YieldPredictionResponse {
  result: YieldResult;
  market_analysis: MarketAnalysis;
  crops: string[];
}

// ---------------------------------------------------------------------------
// Seed viability (/api/seed-viability)
// ---------------------------------------------------------------------------
export interface SeedViabilityResult {
  classical: string;
  quantum: string;
  ensemble: string;
  agreement?: boolean;
  /** Held-out model probability of viability, 0-100. */
  viability_score?: number | null;
  /** "Grade A" | "Grade B" | "Grade C" — derived, not an official certification. */
  quality_class?: string | null;
  quality_source?: string | null;
  error?: string;
}

export interface SeedViabilityResponse {
  result: SeedViabilityResult;
}

// ---------------------------------------------------------------------------
// Storage recommendation (/api/storage-recommendation)
// ---------------------------------------------------------------------------
export interface StorageSpecs {
  temp: string;
  hum: string;
  pres: string;
  shelf_life: string;
  fungus: string;
  insects: string;
  risk_score: number;
  /** e.g. "knowledge_base/storage_db.json#Rice"; null when the KB has no entry. */
  source?: string | null;
  /**
   * "static_knowledge_base" when this crop has its own KB entry, or
   * "generic_default" when no crop-specific protocol exists and generic
   * guideline values were substituted.
   */
  data_type?: "static_knowledge_base" | "generic_default" | string;
  /** True only when the values come from this crop's own KB entry. */
  crop_specific?: boolean;
  /** Always false: the storage KB is not live sensor/weather telemetry. */
  live_telemetry?: boolean;
  /** Explicit non-live statement to surface in the UI. */
  protocol_note?: string | null;
  /** Human-readable explanation of where the values come from. */
  note?: string | null;
}

export interface StorageRecommendationResponse {
  result: StorageSpecs;
  crop: string;
  crops: string[];
}

// ---------------------------------------------------------------------------
// Quantum ML (/api/quantum-ml)
// ---------------------------------------------------------------------------
export interface QuantumMLResult {
  crop_rf: string;
  crop_vqc: string;
  yield_xgb: number;
  yield_vqr: number;
  seed_svm: string;
  seed_vqc: string;
  prob_success: number;
  decision: string;
  /** Set when one of the legs could not run and mirrors its classical value. */
  notes?: string[];
  error?: string;
}

export interface QuantumMLResponse {
  result: QuantumMLResult;
  inputs: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Dashboard (/api/dashboard)
// ---------------------------------------------------------------------------
export interface DashboardMetrics {
  rf: string;
  xgb: string;
  svm: string;
  meta: string;
  /** "training_registry.json" or "unavailable". */
  source?: string;
  note?: string;
  provenance?: Record<
    string,
    | {
        basis: string;
        recorded_at?: string | null;
        run_id?: string | null;
        algorithm?: string | null;
      }
    | null
  >;
}

export interface PredictionHistoryItem {
  type: string;
  inputs: Record<string, unknown>;
  results: Record<string, unknown>;
  timestamp: string;
}

export interface DashboardResponse {
  username: string;
  // Model-performance metrics are admin-only; null for guests and regular users.
  metrics: DashboardMetrics | null;
  history: PredictionHistoryItem[];
  total_runs: number;
  avg_yield: number;
  viability_rate: number;
  top_crop: string;
}

// ---------------------------------------------------------------------------
// District storage intelligence (/api/districts/storage-live,
// /api/notifications/district-storage)
// ---------------------------------------------------------------------------
export type RiskLevel = "CRITICAL" | "WARNING" | "MONITOR" | "STABLE";

export interface DistrictSeedStorage {
  available_stock_tons: number;
  total_capacity_tons: number;
  occupancy_percentage: number;
  current_viability_percentage: number;
  predicted_viability_percentage: number;
  moisture_vulnerability: string;
  risk_level: RiskLevel;
  alert_message: string;
  redistribution_eligible: boolean;
}

export interface DistrictCropStorage {
  facility_type: string;
  optimal_temp: string;
  optimal_humidity: string;
  safe_shelf_life: string;
  pest_and_fungus_risk: string;
  preservation_protocol: string;
  risk_score: number;
}

export interface DistrictStorage {
  district_id: string;
  district_name: string;
  kannada_name: string;
  region: string;
  primary_crop: string;
  seed_storage: DistrictSeedStorage;
  crop_storage: DistrictCropStorage;
}

export interface StorageLiveResponse {
  status: string;
  last_updated: string;
  next_sync_in_seconds: number;
  summary: {
    total_districts: number;
    critical_alerts: number;
    warning_alerts: number;
    stable_districts: number;
    total_stock_tons: number;
    total_capacity_tons: number;
    statewide_occupancy_percentage: number;
  };
  districts: DistrictStorage[];
}

export interface DistrictNotification {
  id: string;
  district_id: string;
  district_name: string;
  kannada_name: string;
  region: string;
  crop: string;
  risk_level: RiskLevel;
  current_viability: number;
  predicted_viability: number;
  stock_tons: number;
  capacity_tons: number;
  occupancy_pct: number;
  moisture_risk: string;
  facility: string;
  safe_duration: string;
  title: string;
  message: string;
  recommended_action: string;
  timestamp: string;
  time_ago: string;
  redistribution_eligible: boolean;
}

export interface DistrictNotificationsResponse {
  status: string;
  next_sync_in_seconds: number;
  critical_count: number;
  warning_count: number;
  monitor_count: number;
  stable_count: number;
  notifications_count: number;
  notifications: DistrictNotification[];
}

// ---------------------------------------------------------------------------
// Datasets (/api/datasets, /api/datasets/upload)
// ---------------------------------------------------------------------------
export interface DatasetEntry {
  id: string;
  name: string;
  rows: string;
  size: string;
  date: string;
  status: string;
  type: string;
}

// ---------------------------------------------------------------------------
// Admin (/api/admin/users, /api/admin/activity-logs)
// ---------------------------------------------------------------------------
export interface AdminUser {
  id: string | number;
  username: string;
  email: string;
  display_name: string;
  role: string;
  provider: string;
  created_at: string;
}

export interface AdminUsersResponse {
  status: string;
  total_users: number;
  users: AdminUser[];
}

export interface ActivityLogEntry {
  id: number;
  user_id: string | number | null;
  event_type: string;
  details: Record<string, unknown>;
  status: string;
  ip_address: string;
  created_at: string;
}

export interface ActivityLogsResponse {
  status: string;
  count: number;
  logs: ActivityLogEntry[];
}

export interface RetrainResponse {
  status: string;
  output?: string;
  error?: string;
  message?: string;
  /** Structured result written by train_all_models.py --report. */
  report?: RetrainReport | null;
}

// ---------------------------------------------------------------------------
// Retraining report (reports/retrain_report.json via /api/retrain)
// ---------------------------------------------------------------------------
export interface RetrainDatasetMeta {
  domain: string;
  path: string | null;
  records: number;
  features: number;
  classes?: number | null;
  synthetic: boolean;
  sha256_16?: string | null;
  provenance: string;
}

export interface ClassificationMetrics {
  accuracy: number;
  precision_macro: number;
  recall_macro: number;
  f1_macro: number;
}

export interface RegressionMetrics {
  r2: number;
  mae: number;
  rmse: number;
}

export interface CrossValidationMetrics {
  accuracy_mean?: number;
  accuracy_std?: number | null;
  r2_mean?: number;
  r2_std?: number | null;
  folds?: number[];
  note?: string;
}

export interface RetrainModelReport {
  domain?: string | null;
  name: string;
  artifact: string;
  task?: string;
  train?: ClassificationMetrics | RegressionMetrics | null;
  cv?: CrossValidationMetrics | null;
  test?: ClassificationMetrics | RegressionMetrics | null;
  params?: Record<string, unknown>;
  gap: number;
  gap_status: "good" | "moderate" | "high" | string;
  simulated_quantum?: boolean;
  dataset_provenance?: string | null;
  features?: number | null;
  classes?: number | null;
  sample_counts?: Record<string, number> | null;
  label_definition?: string;
  base_rate_train?: number;
  base_rate_test?: number;
}

export interface RetrainReport {
  run_id: string;
  timestamp: string;
  success: boolean;
  error?: string | null;
  quantum_mode: string;
  duration_seconds?: number;
  datasets: RetrainDatasetMeta[];
  models: RetrainModelReport[];
  meta?: RetrainModelReport;
  generalization?: {
    status: string;
    max_gap_model?: string;
    max_gap?: number;
    summary?: string;
  };
  registry_entries_added?: number;
  notes?: string[];
}

// ---------------------------------------------------------------------------
// Model metrics (/api/model_metrics) — the Model Confidence card
// ---------------------------------------------------------------------------
export interface ModelMetricEntry {
  model_name: string;
  domain?: string | null;
  algorithm?: string | null;
  task?: "classification" | "regression" | string;
  timestamp?: string | null;
  run_id?: string | null;
  train?: ClassificationMetrics | RegressionMetrics | Record<string, unknown> | null;
  cv?: CrossValidationMetrics | Record<string, unknown> | null;
  test?: ClassificationMetrics | RegressionMetrics | Record<string, unknown> | null;
  generalization?: { train_test_gap?: number; status?: string } | null;
  records?: number | null;
  features_count?: number | null;
  classes?: number | null;
  sample_counts?: Record<string, number> | null;
  dataset_provenance?: string | null;
  simulated_quantum?: boolean;
  artifact_written?: boolean;
  notes?: string | null;
}

export interface ModelMetricsResponse {
  available: boolean;
  note?: string;
  entry_count?: number;
  last_run_id?: string | null;
  last_run_at?: string | null;
  generalization?: { status: string };
  headline?: DashboardMetrics;
  models: ModelMetricEntry[];
}

// ---------------------------------------------------------------------------
// MLOps & experiment tracking (/api/experiments, /api/model_versions,
// /api/test_runs, /api/training_history, /api/hyperparameter_trials)
// ---------------------------------------------------------------------------
export interface ExperimentRecord {
  id: number;
  experiment_id: string;
  timestamp: string;
  model_name: string;
  task_name: string;
  dataset_name: string;
  dataset_hash?: string | null;
  dataset_version?: string | null;
  random_seed?: number | null;
  status: string;
  error_message?: string | null;
  data_quality_status?: string | null;
  leakage_status?: string | null;
  overfitting_status?: string | null;
  baseline_score?: number | null;
  model_score?: number | null;
  validation_status?: string | null;
  training_time?: number | null;
  inference_time?: number | null;
  best_trial_id?: number | null;
  model_path?: string | null;
  created_at: string;
}

export interface ExperimentMetric {
  id: number;
  experiment_id: string;
  metric_name: string;
  metric_value: number;
  split: string;
  created_at: string;
}

export interface HyperparameterTrial {
  id: number;
  experiment_id: string;
  trial_number: number;
  parameters_json: string;
  cv_score?: number | null;
  validation_score?: number | null;
  training_time?: number | null;
  status: string;
  created_at: string;
}

export interface ExperimentsResponse extends Array<ExperimentRecord> {}

export interface ExperimentDetailsResponse {
  experiment: ExperimentRecord;
  metrics: ExperimentMetric[];
  trials: HyperparameterTrial[];
}

export interface ModelVersion {
  id: number;
  model_name: string;
  version: string;
  experiment_id: string;
  model_path: string;
  dataset_version?: string | null;
  best_parameters_json?: string | null;
  metrics_json?: string | null;
  created_at: string;
  is_production: 0 | 1;
}

export interface ModelVersionsResponse extends Array<ModelVersion> {}

export interface TestRun {
  id: number;
  test_run_id: string;
  timestamp: string;
  status: string;
  total_tests: number;
  passed: number;
  failed: number;
  skipped: number;
  duration: number;
}

export interface TestRunsResponse extends Array<TestRun> {}

export interface TrainingHistoryResponse {
  history: string[];
}

// ---------------------------------------------------------------------------
// Open-Meteo live weather (used by the web dashboard directly)
// ---------------------------------------------------------------------------
export interface OpenMeteoWeather {
  current?: {
    temperature_2m?: number;
    relative_humidity_2m?: number;
    apparent_temperature?: number;
    precipitation?: number;
    weather_code?: number;
    surface_pressure?: number;
    wind_speed_10m?: number;
    uv_index?: number;
  };
  daily?: {
    temperature_2m_max?: number[];
    temperature_2m_min?: number[];
    precipitation_probability_max?: number[];
  };
}
