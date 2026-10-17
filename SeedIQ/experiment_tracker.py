import os
import sqlite3
import json
import hashlib
import datetime

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'seediq.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_experiment_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. experiments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT UNIQUE NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                model_name TEXT NOT NULL,
                task_name TEXT NOT NULL,
                dataset_name TEXT NOT NULL,
                dataset_hash TEXT,
                dataset_version TEXT,
                random_seed INTEGER DEFAULT 42,
                status TEXT DEFAULT 'RUNNING',
                error_message TEXT,
                data_quality_status TEXT,
                leakage_status TEXT,
                overfitting_status TEXT,
                baseline_score REAL,
                model_score REAL,
                validation_status TEXT,
                training_time REAL,
                inference_time REAL,
                best_trial_id INTEGER,
                model_path TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Ensure new columns exist if DB was already created
        cursor.execute("PRAGMA table_info(experiments)")
        cols = [r['name'] for r in cursor.fetchall()]
        for col_name, col_type in [
            ('error_message', 'TEXT'), ('data_quality_status', 'TEXT'),
            ('leakage_status', 'TEXT'), ('overfitting_status', 'TEXT'),
            ('baseline_score', 'REAL'), ('model_score', 'REAL'),
            ('validation_status', 'TEXT')
        ]:
            if col_name not in cols:
                cursor.execute(f"ALTER TABLE experiments ADD COLUMN {col_name} {col_type}")
        
        # 2. experiment_metrics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS experiment_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                split TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
            )
        ''')
        
        # 3. hyperparameter_trials
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS hyperparameter_trials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id TEXT NOT NULL,
                trial_number INTEGER NOT NULL,
                parameters_json TEXT NOT NULL,
                cv_score REAL,
                validation_score REAL,
                training_time REAL,
                status TEXT DEFAULT 'COMPLETED',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
            )
        ''')
        
        # 4. model_versions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                version TEXT NOT NULL,
                experiment_id TEXT NOT NULL,
                model_path TEXT NOT NULL,
                dataset_version TEXT,
                best_parameters_json TEXT,
                metrics_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_production INTEGER DEFAULT 0,
                FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
            )
        ''')
        
        # 5. dataset_versions
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dataset_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_name TEXT NOT NULL,
                version TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                row_count INTEGER,
                column_count INTEGER,
                features_json TEXT,
                target_column TEXT,
                missing_values INTEGER,
                duplicate_rows INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 6. test_runs
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id TEXT UNIQUE NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PASSED',
                total_tests INTEGER DEFAULT 0,
                passed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                duration REAL DEFAULT 0.0
            )
        ''')
        
        # 7. test_results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_run_id TEXT NOT NULL,
                test_name TEXT NOT NULL,
                test_type TEXT DEFAULT 'UNIT',
                status TEXT NOT NULL,
                duration REAL DEFAULT 0.0,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(test_run_id) REFERENCES test_runs(test_run_id)
            )
        ''')
        
        # 8. reports
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT UNIQUE NOT NULL,
                experiment_id TEXT NOT NULL,
                report_type TEXT DEFAULT 'HTML',
                file_path TEXT NOT NULL,
                summary_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
            )
        ''')
        
        conn.commit()
        print("✅ SeedIQ MLOps database tables initialized successfully.")

def calculate_file_hash(filepath):
    """Calculates SHA-256 hash of a dataset file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def register_dataset_version(dataset_name, filepath, target_column):
    import pandas as pd
    if not os.path.exists(filepath):
        return None
        
    df = pd.read_csv(filepath)
    file_hash = calculate_file_hash(filepath)
    row_count, col_count = df.shape
    features = [c for c in df.columns if c != target_column]
    missing_vals = int(df.isnull().sum().sum())
    duplicates = int(df.duplicated().sum())
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Check existing version
        cursor.execute("SELECT version FROM dataset_versions WHERE dataset_name = ? AND file_hash = ?", (dataset_name, file_hash))
        row = cursor.fetchone()
        if row:
            return row['version']
            
        # Create new version string
        cursor.execute("SELECT COUNT(*) as count FROM dataset_versions WHERE dataset_name = ?", (dataset_name,))
        count = cursor.fetchone()['count'] + 1
        version = f"v{count:03d}"
        
        cursor.execute('''
            INSERT INTO dataset_versions 
            (dataset_name, version, file_hash, row_count, column_count, features_json, target_column, missing_values, duplicate_rows)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (dataset_name, version, file_hash, row_count, col_count, json.dumps(features), target_column, missing_vals, duplicates))
        conn.commit()
        return version

def log_hyperparameter_trial(exp_id, trial_num, params_dict, cv_score, val_score=None, train_time=0.0, status='COMPLETED'):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO hyperparameter_trials (experiment_id, trial_number, parameters_json, cv_score, validation_score, training_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (exp_id, trial_num, json.dumps(params_dict), cv_score, val_score, train_time, status))
        conn.commit()

if __name__ == "__main__":
    init_experiment_db()
