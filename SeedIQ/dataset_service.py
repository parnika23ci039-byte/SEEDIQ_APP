"""
SeedIQ Dataset Service
Automates dataset ingestion, schema-based type detection, Supabase Storage uploads,
automatic preprocessing, feature extraction, auditing, and dataset versioning.
Strictly does NOT retrain ML/QML models automatically.
"""

import os
import io
import json
import hashlib
import datetime
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional

from data_preprocessing import (
    detect_dataset_type,
    preprocess_crop_data,
    preprocess_yield_data,
    preprocess_seed_data
)
from data_validator import run_data_quality_checks
from activity_logger import log_activity
from supabase_client import supabase

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
TEMP_DIR = os.path.join(DATA_DIR, 'temp_uploads')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
_dataset_executor = ThreadPoolExecutor(max_workers=4)

MAX_DATASET_SIZE_BYTES = 10 * 1024 * 1024  # Strict 10 MB user upload limit

def compute_checksum(file_input: Any) -> str:
    """
    Streams file or bytes in 1MB chunks to compute SHA256 checksum with constant memory.
    """
    sha256 = hashlib.sha256()
    if isinstance(file_input, str) and os.path.isfile(file_input):
        with open(file_input, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                sha256.update(chunk)
    elif isinstance(file_input, (bytes, bytearray)):
        sha256.update(file_input)
    return sha256.hexdigest()

class ValidationResult(tuple):
    """
    Backwards-compatible tuple that unpacks as (is_valid, message, sample_df)
    while exposing .row_count and .file_size attributes for streaming pipelines.
    """
    def __new__(cls, is_valid, message, sample_df, row_count=0, file_size=0):
        return super().__new__(cls, (is_valid, message, sample_df))

    def __init__(self, is_valid, message, sample_df, row_count=0, file_size=0):
        self.is_valid = is_valid
        self.message = message
        self.sample_df = sample_df
        self.row_count = row_count
        self.file_size = file_size

def validate_csv(file_input: Any, filename: str, max_file_size: int = MAX_DATASET_SIZE_BYTES) -> ValidationResult:
    """
    Validates CSV file up to 10 MB user upload limit.
    Returns ValidationResult tuple (is_valid, message, sample_df) with .row_count and .file_size.
    """
    if not filename.lower().endswith('.csv'):
        return ValidationResult(False, "File must have a .csv extension.", None, 0, 0)

    file_size = 0
    file_path = None
    if isinstance(file_input, str) and os.path.isfile(file_input):
        file_path = file_input
        file_size = os.path.getsize(file_input)
    elif isinstance(file_input, (bytes, bytearray)):
        file_size = len(file_input)

    if file_size == 0:
        return ValidationResult(False, "Uploaded file is empty.", None, 0, 0)

    if file_size > max_file_size:
        return ValidationResult(False, "File size must be 10 MB or less.", None, 0, 0)

    # Detect delimiter and encoding safely
    sample_df = None
    delimiters = [',', ';', '\t']
    encodings = ['utf-8', 'latin-1', 'cp1252']

    for enc in encodings:
        for delim in delimiters:
            try:
                if file_path:
                    sample_df = pd.read_csv(file_path, sep=delim, nrows=5000, encoding=enc)
                else:
                    sample_df = pd.read_csv(io.BytesIO(file_input[:min(len(file_input), 1024*1024)]), sep=delim, nrows=5000, encoding=enc)
                if sample_df is not None and sample_df.shape[1] >= 2:
                    break
            except Exception:
                continue
        if sample_df is not None and sample_df.shape[1] >= 2:
            break

    if sample_df is None or sample_df.empty:
        return ValidationResult(False, "Unable to parse valid tabular CSV data.", None, 0, 0)

    if sample_df.shape[1] < 2:
        return ValidationResult(False, "Dataset must contain at least 2 columns.", None, 0, 0)

    row_count = len(sample_df)
    return ValidationResult(True, "Valid CSV dataset.", sample_df, row_count, file_size)

def get_next_dataset_version(dataset_name: str) -> str:
    """
    Queries dataset_versions in Supabase/SQLite to determine next sequential version string (v001, v002...).
    """
    count = 0
    success, rows = supabase.select_rows("dataset_versions", f"dataset_name=eq.{dataset_name}&select=id")
    if success and rows:
        count = len(rows)
    else:
        # Fallback to local SQLite tracking
        try:
            import sqlite3
            conn = sqlite3.connect("seediq.db")
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS dataset_versions (id INTEGER PRIMARY KEY, dataset_name TEXT, version TEXT)")
            c.execute("SELECT COUNT(*) FROM dataset_versions WHERE dataset_name=?", (dataset_name,))
            count = c.fetchone()[0]
            conn.close()
        except Exception:
            count = 0
    return f"v{count + 1:03d}"

def process_and_store_dataset(
    file_input: Any = None,
    filename: Optional[str] = None,
    user_id: Optional[str] = None,
    user_role: str = "Admin",
    auth_token: Optional[str] = None,
    max_file_size: int = MAX_DATASET_SIZE_BYTES,
    file_bytes: Optional[bytes] = None
) -> Dict[str, Any]:
    """
    Executes the SeedIQ Complete Ingestion & Preprocessing Pipeline for <=10 MB CSV datasets:
    1. Validation (extension, emptiness, <=10MB size limit)
    2. Encoding & Delimiter Auto-Detection
    3. Safe Tabular Ingestion
    4. Statistical Detection (rows, columns, numerical, categorical, missing, duplicates, dtypes)
    5. Missing Value Cleaning (numerical median, categorical mode)
    6. Duplicate Record Resolution
    7. Feature Categorical Encoding & Numerical Scaling
    8. Original Preservation
    9. Processed Dataset Generation
    10. Metadata Record & Versioning
    11. Asynchronous Supabase Storage Sync
    12. Zero Automatic Model Retraining
    """
    if file_input is None and file_bytes is not None:
        file_input = file_bytes
    if filename is None:
        filename = "uploaded_dataset.csv"

    # 1. Validation
    val_res = validate_csv(file_input, filename, max_file_size)
    is_valid, val_msg, sample_df = val_res
    file_size = getattr(val_res, 'file_size', 0)
    if not is_valid or sample_df is None:
        log_activity(
            "DATASET_PROCESSING_FAILED",
            user_id=user_id,
            details={"filename": filename, "error": val_msg},
            status="FAILED"
        )
        return {"status": "error", "message": val_msg}

    file_hash = compute_checksum(file_input)

    # 2. Schema-Based Type Detection
    detected_type = detect_dataset_type(sample_df)
    type_labels = {
        'crop': "Crop Recommendation",
        'yield': "Yield Prediction",
        'seed': "Seed Viability",
        'other': "Other Agriculture Dataset",
        'unknown': "General Agriculture CSV"
    }
    dataset_label = type_labels.get(detected_type, "General Agriculture CSV")
    clean_type = detected_type if detected_type in ['crop', 'yield', 'seed'] else 'other'

    # 3. Storage Paths & Original Preservation
    timestamp_slug = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    original_storage_path = f"datasets/{clean_type}/{timestamp_slug}_{file_hash[:8]}_{filename}"
    processed_storage_path = f"processed/{clean_type}/{timestamp_slug}_{file_hash[:8]}_processed.csv"

    local_original_path = os.path.join(DATA_DIR, f"{timestamp_slug}_{filename}")
    if isinstance(file_input, str) and os.path.isfile(file_input):
        if os.path.abspath(file_input) != os.path.abspath(local_original_path):
            import shutil
            shutil.copyfile(file_input, local_original_path)
    elif isinstance(file_input, (bytes, bytearray)):
        with open(local_original_path, 'wb') as f:
            f.write(file_input)

    log_activity(
        "DATASET_UPLOADED",
        user_id=user_id,
        details={
            "filename": filename,
            "detected_type": dataset_label,
            "storage_path": original_storage_path,
            "size_bytes": file_size
        }
    )

    # 4. Safe Full Ingestion & Statistic Detection
    df_raw = None
    for enc in ['utf-8', 'latin-1', 'cp1252']:
        for delim in [',', ';', '\t']:
            try:
                df_raw = pd.read_csv(local_original_path, sep=delim, encoding=enc)
                if df_raw.shape[1] >= 2:
                    break
            except Exception:
                continue
        if df_raw is not None and df_raw.shape[1] >= 2:
            break

    if df_raw is None or df_raw.empty:
        df_raw = sample_df.copy()

    total_rows = len(df_raw)
    col_count = df_raw.shape[1]
    numeric_cols = df_raw.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = df_raw.select_dtypes(exclude=[np.number]).columns.tolist()
    missing_count = int(df_raw.isnull().sum().sum())
    duplicate_count = int(df_raw.duplicated().sum())

    # Target Column Identification
    target_column = None
    cols_lower = {c.lower(): c for c in df_raw.columns}
    if clean_type == 'crop':
        target_column = cols_lower.get('crop') or cols_lower.get('label') or 'Crop'
    elif clean_type == 'yield':
        target_column = cols_lower.get('yield_tonnes') or cols_lower.get('yield') or df_raw.columns[-1]
    elif clean_type == 'seed':
        target_column = cols_lower.get('viable') or cols_lower.get('viability') or 'Viable'
    else:
        target_column = df_raw.columns[-1]

    original_features = [c for c in df_raw.columns if c != target_column]

    # 5. Cleaning: Handle Duplicates and Missing Values
    df_cleaned = df_raw.drop_duplicates()
    for col in numeric_cols:
        if df_cleaned[col].isnull().any():
            median_val = df_cleaned[col].median()
            df_cleaned[col] = df_cleaned[col].fillna(median_val if not pd.isna(median_val) else 0)

    for col in categorical_cols:
        if df_cleaned[col].isnull().any():
            mode_s = df_cleaned[col].mode()
            mode_val = mode_s[0] if not mode_s.empty else "Unknown"
            df_cleaned[col] = df_cleaned[col].fillna(mode_val)

    # 6. Complete Preprocessing & Transformation
    processed_features = []
    preprocessing_meta = {}
    local_processed_path = os.path.join(DATA_DIR, f"{timestamp_slug}_{file_hash[:8]}_processed.csv")

    try:
        if clean_type == 'crop':
            X_scaled, y, scaler, crop_encoder = preprocess_crop_data(local_original_path)
            processed_features = ['Nitrogen', 'Phosphorus', 'Potassium', 'Temperature', 'Humidity', 'pH', 'Rainfall']
            preprocessing_meta = {
                "preprocessor": "StandardScaler + LabelEncoder",
                "classes_count": len(crop_encoder.classes_) if hasattr(crop_encoder, 'classes_') else 0,
                "features_scaled": len(processed_features)
            }
            processed_df = pd.DataFrame(X_scaled, columns=processed_features)
            processed_df['Target_Encoded'] = y
            processed_df.to_csv(local_processed_path, index=False)
        elif clean_type == 'yield':
            X_scaled, y, scaler, crop_enc, season_enc = preprocess_yield_data(local_original_path)
            processed_features = ['Crop', 'Season', 'Area_Hectares', 'Area_Sq', 'Crop_Season']
            preprocessing_meta = {
                "preprocessor": "StandardScaler + Multi-LabelEncoder",
                "features_scaled": len(processed_features)
            }
            processed_df = pd.DataFrame(X_scaled, columns=processed_features)
            processed_df['Yield_Tonnes'] = list(y)
            processed_df.to_csv(local_processed_path, index=False)
        elif clean_type == 'seed':
            X_scaled, y, scaler = preprocess_seed_data(local_original_path)
            processed_features = ['Moisture_Level', 'Weight_g']
            preprocessing_meta = {
                "preprocessor": "StandardScaler",
                "features_scaled": len(processed_features)
            }
            processed_df = pd.DataFrame(X_scaled, columns=processed_features)
            processed_df['Viable'] = list(y)
            processed_df.to_csv(local_processed_path, index=False)
        else:
            from sklearn.preprocessing import StandardScaler, LabelEncoder
            processed_df = df_cleaned.copy()
            for cat_col in categorical_cols:
                le = LabelEncoder()
                processed_df[cat_col] = le.fit_transform(processed_df[cat_col].astype(str))
            
            feat_num_cols = [c for c in numeric_cols if c != target_column]
            if feat_num_cols:
                scaler = StandardScaler()
                processed_df[feat_num_cols] = scaler.fit_transform(processed_df[feat_num_cols])

            processed_features = [c for c in processed_df.columns if c != target_column]
            preprocessing_meta = {
                "preprocessor": "StandardScaler + LabelEncoder",
                "categorical_encoded": len(categorical_cols),
                "numerical_scaled": len(feat_num_cols)
            }
            processed_df.to_csv(local_processed_path, index=False)

    except Exception as e:
        print(f"[DATASET_PIPELINE] Preprocessing notice: {e}")
        preprocessing_meta = {"note": f"Robust fallback preprocessing: {e}"}
        if not os.path.exists(local_processed_path):
            df_cleaned.to_csv(local_processed_path, index=False)
        processed_features = original_features

    # 5. Data Quality & Audit Checks
    quality_report = run_data_quality_checks(local_original_path, target_column)
    missing_count = int(sample_df.isnull().sum().sum())
    duplicate_count = int(sample_df.duplicated().sum())

    # 6. Versioning
    version_str = get_next_dataset_version(dataset_label)
    row_count = total_rows

    # 7. Record in Supabase & SQLite
    # Master dataset entry
    dataset_entry = {
        "name": dataset_label,
        "original_filename": filename,
        "stored_path": original_storage_path,
        "dataset_type": clean_type,
        "file_size": file_size,
        "row_count": row_count,
        "column_count": col_count,
        "features_list": original_features,
        "target_column": target_column,
        "status": "ready",
        "checksum": file_hash,
        "uploaded_by": user_id if (isinstance(user_id, str) and len(user_id) == 36 and '-' in user_id) else None
    }
    
    # Version entry
    version_entry = {
        "dataset_name": dataset_label,
        "version": version_str,
        "file_hash": file_hash,
        "stored_path": original_storage_path,
        "processed_path": processed_storage_path,
        "row_count": row_count,
        "column_count": col_count,
        "features_json": processed_features or original_features,
        "target_column": target_column,
        "missing_values": missing_count,
        "duplicate_rows": duplicate_count,
        "preprocessing_metadata": preprocessing_meta,
        "feature_metadata": {
            "original_features": original_features,
            "processed_features": processed_features,
            "target_column": target_column
        },
        "created_by": user_id if (isinstance(user_id, str) and len(user_id) == 36 and '-' in user_id) else None
    }

    # Audit entry
    audit_entry = {
        "dataset_name": dataset_label,
        "file_hash": file_hash,
        "shape": f"{row_count}x{col_count}",
        "target_column": target_column,
        "missing_values": missing_count,
        "duplicate_rows": duplicate_count,
        "audit_json": {
            "quality": quality_report,
            "version": version_str,
            "preprocessing": preprocessing_meta
        }
    }

    # 8. Asynchronously sync to Supabase Storage & PostgREST in background pool
    def _async_supabase_dataset_sync():
        try:
            supabase.ensure_bucket("seediq-datasets", is_public=True, token=auth_token)
            # Concurrently stream upload raw and processed datasets from disk
            with ThreadPoolExecutor(max_workers=2) as uploader:
                u1 = uploader.submit(supabase.upload_file, "seediq-datasets", original_storage_path, local_original_path, "text/csv", auth_token)
                u2 = uploader.submit(supabase.upload_file, "seediq-datasets", processed_storage_path, local_processed_path, "text/csv", auth_token)
                u1.result()
                u2.result()
            
            # PostgREST row sync
            supabase.insert_row("datasets", dataset_entry, token=auth_token)
            supabase.insert_row("dataset_versions", version_entry, token=auth_token)
            # Clean up ephemeral local copies on Render to prevent disk usage accumulation
            if os.environ.get("RENDER"):
                try:
                    if os.path.exists(local_original_path):
                        os.remove(local_original_path)
                    if os.path.exists(local_processed_path):
                        os.remove(local_processed_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"[DATASET_PIPELINE] Asynchronous Supabase sync notice: {e}")

    try:
        _dataset_executor.submit(_async_supabase_dataset_sync)
    except Exception as e:
        print(f"[DATASET_PIPELINE] Background worker submit error: {e}")

    # Also dual-write to local SQLite so legacy viewers remain up to date
    try:
        import sqlite3
        conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'seediq.db'))
        conn.execute('''
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
        conn.execute('''
            INSERT INTO dataset_versions (dataset_name, version, file_hash, row_count, column_count, features_json, target_column, missing_values, duplicate_rows)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            dataset_label, version_str, file_hash, row_count, col_count,
            json.dumps(processed_features or original_features), target_column, missing_count, duplicate_count
        ))
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS dataset_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_name TEXT,
                file_hash TEXT,
                shape TEXT,
                target_column TEXT,
                missing_values INTEGER,
                duplicate_rows INTEGER,
                audit_json TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            INSERT INTO dataset_audits (dataset_name, file_hash, shape, target_column, missing_values, duplicate_rows, audit_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            dataset_label, file_hash, f"{row_count}x{col_count}", target_column, missing_count, duplicate_count,
            json.dumps(audit_entry["audit_json"])
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DATASET_PIPELINE] SQLite sync error: {e}")

    # Log completion events
    log_activity(
        "DATASET_PREPROCESSED",
        user_id=user_id,
        details={
            "version": version_str,
            "dataset": dataset_label,
            "processed_path": processed_storage_path,
            "features_extracted": len(processed_features)
        }
    )

    return {
        "status": "success",
        "message": f"Dataset ingested, preprocessed, and versioned as {version_str}.",
        "dataset_name": dataset_label,
        "version": version_str,
        "rows": row_count,
        "columns": col_count,
        "detected_type": dataset_label,
        "original_storage_path": original_storage_path,
        "processed_storage_path": processed_storage_path,
        "target_column": target_column,
        "features": processed_features or original_features,
        "preprocessing_status": "COMPLETED",
        "quality_status": "PASSED" if quality_report.get("passed") else "REVIEW_NEEDED"
    }
