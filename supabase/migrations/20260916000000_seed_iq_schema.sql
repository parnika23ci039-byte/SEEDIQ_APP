-- ==============================================================================
-- SeedIQ Supabase PostgreSQL Migration
-- Migration: 20260916000000_seed_iq_schema.sql
-- ==============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. PROFILES (Extends auth.users with SeedIQ roles & metadata)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'Farmer' CHECK (role IN ('Admin', 'Researcher', 'Farmer', 'Guest')),
    provider TEXT DEFAULT 'email',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_username ON public.profiles(username);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);

-- ------------------------------------------------------------------------------
-- 2. PREDICTIONS (User prediction telemetry ledger)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.predictions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    prediction_type TEXT NOT NULL CHECK (prediction_type IN ('crop', 'yield', 'seed', 'storage', 'quantum')),
    inputs JSONB NOT NULL DEFAULT '{}'::jsonb,
    results JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_user_id ON public.predictions(user_id);
CREATE INDEX IF NOT EXISTS idx_predictions_user_timestamp ON public.predictions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_user_type ON public.predictions(user_id, prediction_type);

-- ------------------------------------------------------------------------------
-- 3. DATASETS (Master dataset metadata catalogue)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    dataset_type TEXT NOT NULL CHECK (dataset_type IN ('crop', 'yield', 'seed', 'other')),
    file_size BIGINT DEFAULT 0,
    row_count INTEGER DEFAULT 0,
    column_count INTEGER DEFAULT 0,
    features_list JSONB DEFAULT '[]'::jsonb,
    target_column TEXT,
    status TEXT DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'validating', 'processing', 'ready', 'failed')),
    processing_error TEXT,
    checksum TEXT,
    uploaded_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_datasets_type ON public.datasets(dataset_type);
CREATE INDEX IF NOT EXISTS idx_datasets_status ON public.datasets(status);
CREATE INDEX IF NOT EXISTS idx_datasets_uploaded_by ON public.datasets(uploaded_by);

-- ------------------------------------------------------------------------------
-- 4. DATASET_VERSIONS (Version lineage and audit statistics)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.dataset_versions (
    id BIGSERIAL PRIMARY KEY,
    dataset_id UUID REFERENCES public.datasets(id) ON DELETE CASCADE,
    dataset_name TEXT NOT NULL,
    version TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    processed_path TEXT,
    row_count INTEGER DEFAULT 0,
    column_count INTEGER DEFAULT 0,
    features_json JSONB DEFAULT '[]'::jsonb,
    target_column TEXT,
    missing_values INTEGER DEFAULT 0,
    duplicate_rows INTEGER DEFAULT 0,
    preprocessing_metadata JSONB DEFAULT '{}'::jsonb,
    feature_metadata JSONB DEFAULT '{}'::jsonb,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dataset_versions_dataset_id ON public.dataset_versions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_name_ver ON public.dataset_versions(dataset_name, version);
CREATE INDEX IF NOT EXISTS idx_dataset_versions_hash ON public.dataset_versions(file_hash);

-- ------------------------------------------------------------------------------
-- 5. DATASET_AUDITS (Quality and leakage audit reports)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.dataset_audits (
    id BIGSERIAL PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    file_hash TEXT,
    shape TEXT,
    target_column TEXT,
    missing_values INTEGER DEFAULT 0,
    duplicate_rows INTEGER DEFAULT 0,
    audit_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dataset_audits_name ON public.dataset_audits(dataset_name);

-- ------------------------------------------------------------------------------
-- 6. EXPERIMENTS (ML / QML experiment tracking)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.experiments (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT UNIQUE NOT NULL,
    model_name TEXT NOT NULL,
    task_name TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    dataset_hash TEXT,
    dataset_version TEXT,
    random_seed INTEGER DEFAULT 42,
    status TEXT DEFAULT 'STARTED',
    training_time DOUBLE PRECISION DEFAULT 0.0,
    inference_time DOUBLE PRECISION DEFAULT 0.0,
    best_trial_id INTEGER,
    model_path TEXT,
    error_message TEXT,
    data_quality_status TEXT,
    leakage_status TEXT,
    overfitting_status TEXT,
    baseline_score DOUBLE PRECISION,
    model_score DOUBLE PRECISION,
    validation_status TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiments_exp_id ON public.experiments(experiment_id);
CREATE INDEX IF NOT EXISTS idx_experiments_model_task ON public.experiments(model_name, task_name);

-- ------------------------------------------------------------------------------
-- 7. EXPERIMENT_METRICS (Per-split evaluation metrics)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.experiment_metrics (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES public.experiments(experiment_id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    split TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_experiment_metrics_exp_id ON public.experiment_metrics(experiment_id);

-- ------------------------------------------------------------------------------
-- 8. HYPERPARAMETER_TRIALS (Optimization search trials)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.hyperparameter_trials (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES public.experiments(experiment_id) ON DELETE CASCADE,
    trial_number INTEGER NOT NULL,
    parameters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    cv_score DOUBLE PRECISION,
    validation_score DOUBLE PRECISION,
    training_time DOUBLE PRECISION DEFAULT 0.0,
    status TEXT DEFAULT 'COMPLETED',
    dataset TEXT,
    task TEXT,
    model TEXT,
    trial_id TEXT,
    hyperparameters TEXT,
    cv_mean DOUBLE PRECISION,
    cv_std DOUBLE PRECISION,
    cv_fold_scores JSONB DEFAULT '[]'::jsonb,
    train_score DOUBLE PRECISION,
    test_score DOUBLE PRECISION,
    all_applicable_metrics JSONB DEFAULT '{}'::jsonb,
    prediction_time DOUBLE PRECISION DEFAULT 0.0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hyperparameter_trials_exp_id ON public.hyperparameter_trials(experiment_id);

-- ------------------------------------------------------------------------------
-- 9. MODEL_VERSIONS (Model artifact registry)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.model_versions (
    id BIGSERIAL PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    experiment_id TEXT REFERENCES public.experiments(experiment_id) ON DELETE SET NULL,
    model_path TEXT NOT NULL,
    dataset_version TEXT,
    best_parameters_json JSONB DEFAULT '{}'::jsonb,
    metrics_json JSONB DEFAULT '{}'::jsonb,
    is_production BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_versions_name ON public.model_versions(model_name, version);

-- ------------------------------------------------------------------------------
-- 10. REPORTS (Generated experiment reports)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.reports (
    id BIGSERIAL PRIMARY KEY,
    report_id TEXT UNIQUE NOT NULL,
    experiment_id TEXT REFERENCES public.experiments(experiment_id) ON DELETE CASCADE,
    report_type TEXT DEFAULT 'HTML',
    file_path TEXT NOT NULL,
    summary_json JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_id ON public.reports(report_id);
CREATE INDEX IF NOT EXISTS idx_reports_exp_id ON public.reports(experiment_id);

-- ------------------------------------------------------------------------------
-- 11. CROSS_VALIDATION_RESULTS (K-Fold CV details)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cross_validation_results (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT,
    model_name TEXT,
    cv_mean DOUBLE PRECISION,
    cv_std DOUBLE PRECISION,
    scores_json JSONB DEFAULT '[]'::jsonb,
    dataset TEXT,
    task TEXT,
    cv_min DOUBLE PRECISION,
    cv_max DOUBLE PRECISION,
    fold_scores_json JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cv_results_exp_id ON public.cross_validation_results(experiment_id);

-- ------------------------------------------------------------------------------
-- 12. ROBUSTNESS_RESULTS (Model stability & perturbation metrics)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.robustness_results (
    id BIGSERIAL PRIMARY KEY,
    experiment_id TEXT,
    model_name TEXT,
    mean_test_score DOUBLE PRECISION,
    std_test_score DOUBLE PRECISION,
    min_test_score DOUBLE PRECISION,
    max_test_score DOUBLE PRECISION,
    details_json JSONB DEFAULT '{}'::jsonb,
    dataset TEXT,
    task TEXT,
    seeds_evaluated JSONB DEFAULT '[]'::jsonb,
    scores_json JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_robustness_exp_id ON public.robustness_results(experiment_id);

-- ------------------------------------------------------------------------------
-- 13. TEST_RUNS (Automated test suite summaries)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.test_runs (
    id BIGSERIAL PRIMARY KEY,
    test_run_id TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'PASSED',
    total_tests INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    duration DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_runs_id ON public.test_runs(test_run_id);

-- ------------------------------------------------------------------------------
-- 14. TEST_RESULTS (Individual test execution cases)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.test_results (
    id BIGSERIAL PRIMARY KEY,
    test_run_id TEXT NOT NULL REFERENCES public.test_runs(test_run_id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    test_type TEXT DEFAULT 'UNIT',
    status TEXT NOT NULL,
    duration DOUBLE PRECISION DEFAULT 0.0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_results_run_id ON public.test_results(test_run_id);

-- ------------------------------------------------------------------------------
-- 15. ACTIVITY_LOGS (Audit & security event stream)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.activity_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    status TEXT DEFAULT 'SUCCESS',
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON public.activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_event ON public.activity_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON public.activity_logs(created_at DESC);

-- ------------------------------------------------------------------------------
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ------------------------------------------------------------------------------
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dataset_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dataset_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.experiments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.experiment_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hyperparameter_trials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cross_validation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.robustness_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.test_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.test_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activity_logs ENABLE ROW LEVEL SECURITY;

-- Profiles: user reads/updates own, Admin reads all
CREATE POLICY "profiles_select_policy" ON public.profiles
    FOR SELECT USING (
        auth.uid() = id OR 
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('Admin', 'Researcher'))
    );

CREATE POLICY "profiles_update_policy" ON public.profiles
    FOR UPDATE USING (auth.uid() = id);

-- Predictions: user accesses own predictions, Admin/Researcher can view analytics
CREATE POLICY "predictions_user_select" ON public.predictions
    FOR SELECT USING (
        auth.uid() = user_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('Admin', 'Researcher'))
    );

CREATE POLICY "predictions_user_insert" ON public.predictions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Datasets: Authenticated users can read datasets; Admin/Researcher can manage
CREATE POLICY "datasets_select_policy" ON public.datasets
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "datasets_modify_policy" ON public.datasets
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('Admin', 'Researcher'))
    );

-- Dataset Versions: Authenticated users can view; Admin/Researcher manage
CREATE POLICY "dataset_versions_select_policy" ON public.dataset_versions
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "dataset_versions_modify_policy" ON public.dataset_versions
    FOR ALL USING (
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN ('Admin', 'Researcher'))
    );

-- Activity Logs: Users read own logs, Admin reads all
CREATE POLICY "activity_logs_select" ON public.activity_logs
    FOR SELECT USING (
        auth.uid() = user_id OR
        EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'Admin')
    );

CREATE POLICY "activity_logs_insert" ON public.activity_logs
    FOR INSERT WITH CHECK (auth.role() = 'authenticated' OR auth.uid() = user_id);

-- General MLOps tables: readable by authenticated users, modifiable by Admin/Researcher
DO $$
DECLARE
    t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY[
        'dataset_audits', 'experiments', 'experiment_metrics',
        'hyperparameter_trials', 'model_versions', 'reports',
        'cross_validation_results', 'robustness_results', 'test_runs', 'test_results'
    ]) LOOP
        EXECUTE format('
            CREATE POLICY "%s_read" ON public.%I FOR SELECT USING (auth.role() = ''authenticated'');
            CREATE POLICY "%s_admin_modify" ON public.%I FOR ALL USING (
                EXISTS (SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role IN (''Admin'', ''Researcher''))
            );
        ', t, t, t, t);
    END LOOP;
END $$;

-- ------------------------------------------------------------------------------
-- STORAGE BUCKETS AND STORAGE OBJECT POLICIES
-- ------------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public)
VALUES ('seediq-datasets', 'seediq-datasets', false)
ON CONFLICT (id) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Allow authenticated reads on seediq-datasets'
    ) THEN
        CREATE POLICY "Allow authenticated reads on seediq-datasets"
        ON storage.objects FOR SELECT
        TO authenticated
        USING (bucket_id = 'seediq-datasets');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Allow authenticated uploads on seediq-datasets'
    ) THEN
        CREATE POLICY "Allow authenticated uploads on seediq-datasets"
        ON storage.objects FOR INSERT
        TO authenticated
        WITH CHECK (bucket_id = 'seediq-datasets');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname = 'storage' AND tablename = 'objects' AND policyname = 'Allow authenticated updates on seediq-datasets'
    ) THEN
        CREATE POLICY "Allow authenticated updates on seediq-datasets"
        ON storage.objects FOR UPDATE
        TO authenticated
        USING (bucket_id = 'seediq-datasets');
    END IF;
END $$;

