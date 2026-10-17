import os
import random
import secrets
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import pickle
import json
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import socket
import requests

# Optimize network DNS on Windows to avoid 10-second IPv6 fallback delays
try:
    _orig_getaddrinfo = socket.getaddrinfo
    def _ipv4_preferred_getaddrinfo(host, port, family=0, *args, **kwargs):
        if family == 0:
            family = socket.AF_INET
        return _orig_getaddrinfo(host, port, family, *args, **kwargs)
    socket.getaddrinfo = _ipv4_preferred_getaddrinfo
except Exception:
    pass


# ==============================================================================
# ENVIRONMENT VARIABLE INITIALIZATION (python-dotenv)
# ==============================================================================
# Resolve absolute paths based on file/project directory, NOT the current working directory.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKSPACE_DIR = os.path.abspath(os.path.join(_APP_DIR, ".."))
_ROOT_ENV = os.path.abspath(os.path.join(_WORKSPACE_DIR, ".env"))
_APP_ENV = os.path.abspath(os.path.join(_APP_DIR, ".env"))

_resolved_env_file = None

try:
    from dotenv import load_dotenv, dotenv_values

    # 1. Support SeedIQ/.env (loaded first)
    if os.path.isfile(_APP_ENV):
        load_dotenv(dotenv_path=_APP_ENV, override=True)
        _resolved_env_file = _APP_ENV

    # 2. Support workspace root .env with priority (overrides SeedIQ/.env)
    if os.path.isfile(_ROOT_ENV):
        root_vals = dotenv_values(_ROOT_ENV)
        for k, v in root_vals.items():
            if v is not None and v.strip() != "":
                os.environ[k] = v.strip()
            elif k not in os.environ:
                os.environ[k] = ""
        _resolved_env_file = _ROOT_ENV

    # 3. Strip surrounding whitespace from all loaded values in os.environ
    for k in list(os.environ.keys()):
        if isinstance(os.environ[k], str):
            os.environ[k] = os.environ[k].strip()

except Exception as _e:
    pass

import qml_model
# The served classical yield artifact is a yield_model.LogPerHaRegressor. Importing
# it here guarantees the class is registered before models/yield_prediction/*.pkl
# is unpickled (pickle resolves the class by module name at load time), so a
# missing module fails loudly at startup instead of on the first prediction.
from yield_model import LogPerHaRegressor  # noqa: F401  (registered for unpickling)
# Experimental district-level yield contract (Crop + District -> t/ha). Its own
# artifact lives under models/experimental/ and never touches the served model.
from experimental_yield_contract import (
    ExperimentalModelUnavailable,
    UnsupportedInputError,
    contract as experimental_yield_contract,
)
from yield_semantics import (
    AREA_KIND_FIELD,
    BASIS_DESCRIPTIONS,
    BASIS_DISTRICT_AGGREGATE,
    UNIT_TOTAL,
    AreaSemanticsError,
    scale_per_hectare_to_total,
)
# Seed counterpart: the single source of truth for turning a seed class index into
# the verdict shown to users and into the 0/1 meta feature. train_all_models.py
# imports the same module, so the two encodings cannot drift apart.
from seed_viability_semantics import viable_flag_from_label, viable_label
from supabase_client import supabase
from activity_logger import log_activity, purge_activity_logs
from dataset_service import process_and_store_dataset
import phone_auth

app = Flask(__name__)

# CORS only affects browsers: the Android client sends no Origin header and is
# untouched by this. Reflecting *every* origin while allowing credentials would
# let any website read authenticated responses, so the allowlist is explicit.
# (The session cookie is SameSite=Lax by default, but that is defence in depth,
# not a substitute for an allowlist.) Widen it per deployment with
# SEEDIQ_CORS_ORIGINS, a comma-separated list of origins or regexes.
DEFAULT_CORS_ORIGINS = [
    "https://sublime-ambition-production-488f.up.railway.app",
    r"https://[a-z0-9-]+\.up\.railway\.app",
    r"https://[a-z0-9-]+\.vercel\.app",
    r"http://localhost(:\d+)?",
    r"http://127\.0\.0\.1(:\d+)?",
]
cors_origins = [o.strip() for o in (os.environ.get("SEEDIQ_CORS_ORIGINS") or "").split(",") if o.strip()]
CORS(app, supports_credentials=True, origins=cors_origins or DEFAULT_CORS_ORIGINS)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "seediq_super_secret_key_quantum_default_fallback_2026")
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Strict 10 MB individual user upload limit
app.config['UPLOAD_FOLDER'] = 'data'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('models', exist_ok=True)

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "File size must be 10 MB or less."}), 413

def log_smtp_startup_status():
    sender_email = (os.environ.get("GMAIL_SENDER_EMAIL") or "").strip()
    sender_password = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    is_email_set = bool(sender_email)
    is_pass_set = bool(sender_password)
    is_ready = is_email_set and is_pass_set
    
    # Development diagnostic showing resolved .env file path without exposing credentials
    print(f"\n[ENV DIAGNOSTIC] Resolved .env path: {_resolved_env_file if _resolved_env_file else 'None found'}")
    print(f"GMAIL_SENDER_EMAIL configured: {'TRUE' if is_email_set else 'FALSE'}")
    print(f"GMAIL_APP_PASSWORD configured: {'TRUE' if is_pass_set else 'FALSE'}")
    print(f"Gmail SMTP configuration: {'READY' if is_ready else 'NOT READY'}\n")

log_smtp_startup_status()

# Auto-copy generated images from the brain artifacts folder to static/images
def copy_generated_assets():
    import shutil
    src_dir = r"C:\Users\SUMITH R\.gemini\antigravity-ide\brain\f6c87e4f-0939-4832-93e7-625604e2f041"
    dest_dir = r"c:\Users\SUMITH R\Desktop\SeedIQ\static\images"
    os.makedirs(dest_dir, exist_ok=True)
    mappings = {
        "soil_macro_view_1782399357003.png": "soil_macro_view.png",
        "wheat_sunset_field_1782399378384.png": "wheat_sunset_field.png",
        "seed_metabolic_scan_1782399394987.png": "seed_metabolic_scan.png"
    }
    for src_name, dest_name in mappings.items():
        src_path = os.path.join(src_dir, src_name)
        dest_path = os.path.join(dest_dir, dest_name)
        if os.path.exists(src_path):
            try:
                shutil.copy(src_path, dest_path)
                print(f"Auto-copied asset: {dest_name}")
            except Exception as e:
                print(f"Error copying asset {src_name}: {e}")

copy_generated_assets()

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'seediq.db')
REGISTRY_FILE = 'training_registry.json'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _is_admin_session() -> bool:
    """Server-side admin check — never trusts a client-supplied flag."""
    return (session.get('role') or '').lower() == 'admin'

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                email TEXT UNIQUE,
                display_name TEXT,
                role TEXT DEFAULT 'Farmer',
                provider TEXT DEFAULT 'local',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add columns if migrating from older schema
        for col_def in [
            ("email", "TEXT"),
            ("display_name", "TEXT"),
            ("provider", "TEXT DEFAULT 'local'"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT")
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass

        conn.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prediction_type TEXT,
                inputs TEXT,
                results TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp TEXT NOT NULL,
                purpose TEXT DEFAULT 'registration',
                name TEXT DEFAULT '',
                password_hash TEXT DEFAULT '',
                attempts INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            )
        ''')
        
        # Ensure all columns exist on otp_codes
        for col_def in [
            ("purpose", "TEXT DEFAULT 'registration'"),
            ("name", "TEXT DEFAULT ''"),
            ("password_hash", "TEXT DEFAULT ''"),
            ("attempts", "INTEGER DEFAULT 0")
        ]:
            try:
                conn.execute(f"ALTER TABLE otp_codes ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass
                
        # Add performance and integrity indexes
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique 
            ON users(email) 
            WHERE email IS NOT NULL AND email != '';
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_user_id ON predictions(user_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_user_timestamp ON predictions(user_id, timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_user_type ON predictions(user_id, prediction_type);")

        # Phone-number authentication (4-digit verification code) — additive migration.
        phone_auth.ensure_phone_schema(conn)

        conn.commit()

def log_prediction(user_id, prediction_type, inputs, results):
    """Safely logs predictions to Supabase and SQLite for user telemetry."""
    if not user_id or user_id == 999999 or user_id == 'guest' or session.get('is_guest'):
        return

    # 1. Dual-write to Supabase predictions table
    try:
        supabase_uid = session.get('supabase_user_id') or (user_id if isinstance(user_id, str) and len(user_id) == 36 and '-' in user_id else None)
        token = session.get('access_token')
        supabase.insert_row("predictions", {
            "user_id": supabase_uid,
            "prediction_type": prediction_type,
            "inputs": inputs,
            "results": results
        }, token=token)
        log_activity("PREDICTION_CREATED", user_id=supabase_uid or str(user_id), details={"prediction_type": prediction_type})
    except Exception as e:
        print(f"[PREDICTION_LOG] Supabase persistence notice: {e}")

    # 2. Dual-write to SQLite fallback
    try:
        sqlite_uid = session.get('sqlite_user_id') or (user_id if isinstance(user_id, int) else None)
        if sqlite_uid:
            with get_db() as conn:
                conn.execute('''
                    INSERT INTO predictions (user_id, prediction_type, inputs, results)
                    VALUES (?, ?, ?, ?)
                ''', (sqlite_uid, prediction_type, json.dumps(inputs), json.dumps(results)))
                conn.commit()
    except Exception as e:
        print(f"Failed to log prediction to SQLite: {e}")


def _hash_password(password):
    """Hash a password with the scheme this project's stored accounts already use.

    werkzeug's default method is scrypt, which requires `hashlib.scrypt`. That
    attribute is missing on Python builds linked against LibreSSL, so the
    boot-time seeding below raised `AttributeError: module 'hashlib' has no
    attribute 'scrypt'` and the whole application failed to import - with a
    fresh database there was no way to start the server at all. `pbkdf2:sha256`
    is the method every existing row in this database already carries, it is
    available on every Python build, and `check_password_hash` keeps verifying
    both old and new hashes. The iteration count is werkzeug's own default.
    """
    return generate_password_hash(password, method='pbkdf2:sha256')


def initialize_seediq_accounts():
    """Initializes fixed Admin and Researcher accounts from environment variables without overwriting existing passwords."""
    admin_email = os.environ.get("SEEDIQ_ADMIN_EMAIL", "admin@seediq.ai").strip().lower()
    researcher_email = os.environ.get("SEEDIQ_RESEARCHER_EMAIL", "researcher@quantum.org").strip().lower()
    
    with get_db() as conn:
        # 1. Fixed Admin Account
        admin = conn.execute("SELECT id FROM users WHERE email = ?", (admin_email,)).fetchone()
        if not admin:
            u_admin = admin_email.split('@')[0]
            conn.execute(
                # OR IGNORE: gunicorn boots several workers at once, so two of them
                # can pass the SELECT above and race on this INSERT. The worker that
                # loses the race would otherwise abort boot with
                # "UNIQUE constraint failed: users.email" and take the service down
                # on the first start against an empty database.
                "INSERT OR IGNORE INTO users (username, password, email, display_name, role, provider) VALUES (?, ?, ?, ?, 'Admin', 'local')",
                (u_admin, _hash_password("admin123"), admin_email, "System Administrator")
            )
        else:
            conn.execute(
                "UPDATE users SET role = 'Admin', provider = 'local' WHERE email = ?",
                (admin_email,)
            )
            
        # 2. Fixed Researcher Account
        researcher = conn.execute("SELECT id FROM users WHERE email = ?", (researcher_email,)).fetchone()
        if not researcher:
            u_res = researcher_email.split('@')[0]
            conn.execute(
                "INSERT OR IGNORE INTO users (username, password, email, display_name, role, provider) VALUES (?, ?, ?, ?, 'Researcher', 'local')",
                (u_res, _hash_password("research123"), researcher_email, "Lead Researcher")
            )
        else:
            conn.execute(
                "UPDATE users SET role = 'Researcher', provider = 'local' WHERE email = ?",
                (researcher_email,)
            )
        conn.commit()

init_db()
initialize_seediq_accounts()

# MLOps experiment-tracking tables (experiments / model_versions / test_runs).
# Created lazily at boot so the read endpoints answer with an empty catalogue
# instead of raising "no such table" on a fresh deployment.
try:
    from experiment_tracker import init_experiment_db
    init_experiment_db()
except Exception as _mlops_init_err:
    print(f"MLOps tables unavailable at startup: {_mlops_init_err}")

# ------------------------------------------------------------------------------
# Phone-number authentication (client requirement: the phone number is the only
# user login identifier, verified with a 4-digit code).
# ------------------------------------------------------------------------------
phone_auth.register_phone_auth(
    app,
    get_db=get_db,
    log_activity=log_activity,
    generate_password_hash=_hash_password,
    secret_key=app.secret_key,
)
PHONE_ADMIN = phone_auth.ensure_phone_admin_account(get_db, _hash_password)
if PHONE_ADMIN:
    print(f"[PHONE_AUTH] Admin phone account ready: {phone_auth.masked_phone(PHONE_ADMIN)}")

# ---- Security Hardening Hooks & Error Handlers ----
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com https://cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "worker-src blob:;"
    )
    return response

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "File size must be 10 MB or less."}), 413

# ---- Load Models and Preprocessors ----
def load_helper(filename):
    filepath = os.path.join('models', filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return None
    return None

# Base Classical Models (Lazy Loaded on first prediction request)
rf_model = None
xgb_model = None
svm_model = None

# Base Quantum Models (Lazy Loaded on first prediction request)
vqc_crop_model = None
vqc_yield_model = None
vqc_seed_model = None

# Stacking Meta Model (Lazy Loaded on first prediction request)
meta_model = None

# Preprocessing helpers (Lazy Loaded on first prediction request)
crop_scaler = None
crop_encoder = None

STANDARD_CROP_CLASSES = np.array([
    'apple', 'banana', 'blackgram', 'chickpea', 'coconut', 'coffee', 'cotton',
    'grapes', 'jute', 'kidneybeans', 'lentil', 'maize', 'mango', 'mothbeans',
    'mungbean', 'muskmelon', 'orange', 'papaya', 'pigeonpeas', 'pomegranate',
    'rice', 'watermelon'
])

def get_crop_encoder():
    global crop_encoder
    if crop_encoder is None:
        crop_encoder = load_helper('crop_encoder.pkl')
    if crop_encoder is None or not hasattr(crop_encoder, 'classes_') or crop_encoder.classes_ is None or len(crop_encoder.classes_) == 0:
        from sklearn.preprocessing import LabelEncoder
        enc = LabelEncoder()
        enc.classes_ = STANDARD_CROP_CLASSES
        crop_encoder = enc
    return crop_encoder

def decode_crop_name(encoder, class_idx):
    enc = encoder or get_crop_encoder()
    if enc is not None and hasattr(enc, 'classes_') and enc.classes_ is not None and len(enc.classes_) > 0:
        try:
            return enc.inverse_transform([int(class_idx)])[0]
        except Exception:
            idx = int(class_idx) % len(enc.classes_)
            return enc.classes_[idx]
    return 'rice'

yield_scaler = None
yield_crop_encoder = None
yield_season_encoder = None

seed_scaler = None

# -----------------------------------------------------------------------------
# Contract-matched model artifacts
# -----------------------------------------------------------------------------
# `models/` holds two generations of artifacts:
#   * flat pickles produced by early notebook experiments, and
#   * one sub-directory per prediction API (`seed_viability/`, `yield_prediction/`).
# A route must build the feature vector that the artifact it loads was fitted on;
# otherwise scikit-learn raises a feature-name/shape error. That mismatch was the
# reason the seed and yield modules answered with invented constants instead of
# model output. The helper functions below are the single place that knows each
# artifact's schema, and every route that needs those models goes through them.
SEED_VIABILITY_MODEL_FILE = os.path.join('seed_viability', 'randomforest_model.pkl')
SEED_FEATURE_COLUMNS = ['Moisture_Level', 'Weight_g']
SEED_TRAINING_CSV = os.path.join('data', 'seed_viability_data.csv')

# `models/yield_prediction/randomforest_model.pkl` is fitted on the one-hot
# layout that `train_all_models.py` publishes to
# `models/yield_feature_manifest.json`: the field area plus one dummy per crop
# present in the routed yield dataset. The API reads that manifest at inference
# time so training and serving cannot disagree about the column order or the
# crop vocabulary.
#
# Season is NOT part of this contract any more. The active yield table is derived
# from the real ICRISAT district-level source, which has no season column, so
# no Season dummy is invented. Requests may still carry a `season` field for
# backwards compatibility with older clients; it is accepted, reported as
# deprecated and IGNORED by the models.
YIELD_MODEL_FILE = os.path.join('yield_prediction', 'randomforest_model.pkl')
YIELD_MANIFEST_FILE = os.path.join('models', 'yield_feature_manifest.json')
LEGACY_YIELD_FEATURE_COLUMNS = [
    'Area_Hectares',
    'Crop_Maize', 'Crop_Rice', 'Crop_Sugarcane', 'Crop_Wheat',
    'Season_Rabi', 'Season_Zaid',
]
YIELD_FEATURE_COLUMNS = LEGACY_YIELD_FEATURE_COLUMNS
YIELD_TRAINING_CSV = os.path.join('data', 'yield_icrisat_karnataka.csv')
LEGACY_YIELD_TRAINING_CSV = os.path.join('data', 'crop_production_karnataka.csv')

seed_viability_model = None
seed_standardizer = None
_yield_model = None
_yield_vqc_model = None
_yield_crop_options = None
_yield_manifest = None


def get_seed_viability_model():
    """Classical seed-viability classifier (raw moisture % + 100-seed weight)."""
    global seed_viability_model
    if seed_viability_model is None:
        seed_viability_model = load_helper(SEED_VIABILITY_MODEL_FILE)
    return seed_viability_model


def get_seed_vqc_model():
    """Variational quantum classifier fitted on the two seed features."""
    global vqc_seed_model
    if not vqc_seed_model:
        vqc_seed_model = load_helper('vqc_seed_model.pkl')
    return vqc_seed_model


def get_seed_standardizer():
    """Mean/standard deviation the seed VQC was trained with.

    `vqc_seed_model.pkl` was fitted on standardized [moisture, weight] features.
    Feeding it raw percentages measurably degrades it (55% vs 91% agreement with
    the training labels), so the scaling statistics are recomputed from the same
    dataset that trained it instead of being guessed or hard-coded.

    Returns (mean, std) as numpy arrays, or None when the dataset is missing.
    """
    global seed_standardizer
    if seed_standardizer is None:
        # Prefer the scaler saved by the retraining pipeline: the served VQC is
        # trained on the TRAIN-split statistics, so standardizing with those
        # exact values keeps training and inference consistent.
        scaler = load_helper('seed_scaler.pkl')
        if scaler is not None and hasattr(scaler, 'mean_') and hasattr(scaler, 'scale_'):
            seed_standardizer = (np.asarray(scaler.mean_, dtype=float),
                                 np.asarray(scaler.scale_, dtype=float))
        else:
            try:
                df = pd.read_csv(SEED_TRAINING_CSV)
                values = df[SEED_FEATURE_COLUMNS].to_numpy(dtype=float)
                seed_standardizer = (values.mean(axis=0), values.std(axis=0))
            except Exception as e:
                print(f"Seed standardizer unavailable: {e}")
                seed_standardizer = False
    return seed_standardizer or None


def run_seed_models(moisture, weight):
    """Run both seed models. Returns (classical, quantum, notes, probability).

    `quantum` is None when the VQC cannot run, so callers can say so instead of
    passing the classical verdict off as a quantum result. `probability` is the
    classical model's own probability of viability (None when unavailable) and
    is the honest source for any quality tier shown to users.
    """
    model = get_seed_viability_model()
    if model is None:
        return None, None, "Seed viability model is not available on the server.", None

    features = pd.DataFrame([[float(moisture), float(weight)]], columns=SEED_FEATURE_COLUMNS)
    classical = viable_label(model.predict(features)[0])
    probability = None
    try:
        probability = float(model.predict_proba(features)[0][1])
    except Exception as e:
        print(f"Seed viability probability unavailable: {e}")

    notes = []
    quantum = None
    vqc = get_seed_vqc_model()
    scaling = get_seed_standardizer()
    if vqc is not None and scaling is not None:
        try:
            mean, std = scaling
            scaled = (features.to_numpy(dtype=float) - mean) / np.where(std == 0, 1.0, std)
            quantum = viable_label(vqc.predict(scaled)[0])
        except Exception as e:
            notes.append(f"VQC unavailable: {e}")
    else:
        notes.append("VQC unavailable: model or training statistics missing.")

    return classical, quantum, "; ".join(notes), probability


def seed_quality_class(probability):
    """Documented viability tier derived from the classical model probability.

    This is NOT an official certification. It is a thresholded view of the
    model's own probability of viability:
        >= 85% -> Grade A, >= 60% -> Grade B, otherwise Grade C.
    """
    if probability is None:
        return None
    if probability >= 0.85:
        return "Grade A"
    if probability >= 0.60:
        return "Grade B"
    return "Grade C"


def get_yield_model():
    """Classical yield regressor for the (crop, season, area) contract.

    Its target is the dataset's `Yield_Tonnes`, i.e. the harvest of the whole
    plot, so callers divide by the area to report per-hectare yield.
    """
    global _yield_model
    if _yield_model is None:
        _yield_model = load_helper(YIELD_MODEL_FILE)
    return _yield_model


def get_yield_manifest():
    """Feature contract published by training: columns + crop vocabulary.

    Returns {} when the manifest is missing or contradicts the loaded artifact
    (for example an artifact trained before this contract existed), in which
    case callers fall back to the legacy layout. The artifact is checked by its
    own `n_features_in_`, so a mismatched manifest can never be applied to it.
    """
    global _yield_manifest
    if _yield_manifest is None:
        manifest = None
        try:
            with open(YIELD_MANIFEST_FILE, 'r', encoding='utf-8') as f:
                candidate = json.load(f)
            columns = candidate.get('feature_columns')
            model = get_yield_model()
            width = getattr(model, 'n_features_in_', None)
            if isinstance(columns, list) and columns and (
                    width is None or int(width) == len(columns)):
                manifest = candidate
                print(f"[YIELD] Loaded {YIELD_MANIFEST_FILE}: {len(columns)} columns, "
                      f"{len(candidate.get('crop_options') or [])} crops, "
                      f"season_required={candidate.get('season_required')}")
            else:
                print(f"[YIELD] Ignoring {YIELD_MANIFEST_FILE}: {len(columns or [])} manifest "
                      f"columns do not match the served model's {width} inputs.")
        except FileNotFoundError:
            print(f"[YIELD] No {YIELD_MANIFEST_FILE}; using the legacy 7-column layout.")
        except Exception as e:
            print(f"[YIELD] Manifest unreadable ({e}); using the legacy 7-column layout.")
        _yield_manifest = manifest if manifest else {}
    return _yield_manifest


def yield_feature_columns():
    """Column order the served yield artifact expects (manifest first)."""
    columns = get_yield_manifest().get('feature_columns')
    return list(columns) if columns else list(LEGACY_YIELD_FEATURE_COLUMNS)


def yield_contract_info():
    """The yield input contract, reported alongside every yield prediction."""
    manifest = get_yield_manifest()
    return {
        'inputs': ['Crop', 'Area_Hectares'],
        'season_required': False,
        'season_deprecated': True,
        'crops': manifest.get('crop_options') or yield_crop_options(),
        'dataset': manifest.get('dataset'),
        'dataset_provenance': manifest.get('dataset_provenance'),
        'dataset_synthetic': manifest.get('dataset_synthetic'),
        'semantics': manifest.get('semantics'),
    }


def yield_crop_options():
    """Crops present in the yield training dataset (menu order preserved)."""
    global _yield_crop_options
    if _yield_crop_options is None:
        manifest_crops = get_yield_manifest().get('crop_options')
        if manifest_crops:
            _yield_crop_options = [str(c) for c in manifest_crops]
            return _yield_crop_options
        for source in (YIELD_TRAINING_CSV, LEGACY_YIELD_TRAINING_CSV):
            try:
                df = pd.read_csv(source, usecols=['Crop'])
                _yield_crop_options = sorted({str(c) for c in df['Crop'].dropna().unique()},
                                             key=str.lower)
                break
            except Exception as e:
                print(f"Yield crop list unavailable from {source}: {e}")
                _yield_crop_options = []
    return _yield_crop_options or ["Cotton", "Maize", "Rice", "Sugarcane", "Wheat"]


def rule_based_crop(temp, hum, rain, ph):
    """Last-resort agronomic rule of thumb used only when models cannot load.

    Returns names in the same lower-case convention as the crop encoder's
    classes_ so downstream knowledge-base lookups and clients see one format.
    Its output is always returned together with `fallback: "rule-based"` so no
    caller can mistake it for model inference.
    """
    if rain > 150 and temp > 22:
        return "rice" if hum > 70 else "coconut"
    if temp < 25 and rain < 100:
        return "chickpea"  # the cool/dry-season class in this dataset
    if 6.0 <= ph <= 7.5 and temp >= 25:
        return "maize"
    return "mothbeans"


def yield_feature_frame(crop, area):
    """One-hot feature frame matching the ACTIVE yield contract (Crop + Area).

    Season is no longer a feature, so no Season dummy is ever set (the active
    dataset is real ICRISAT district-level data with no season dimension, and a
    season value is neither accepted nor invented). The crop is matched
    case-insensitively against the crops the served artifact was trained on; an
    unrecognised crop leaves every crop dummy at 0, which is the artifact's
    crop-independent estimate — `run_yield_models` reports that explicitly
    instead of presenting it as a crop-specific prediction.
    """
    columns = yield_feature_columns()
    trained_crops = get_yield_manifest().get('crop_options') or []
    row = {name: 0.0 for name in columns}
    row['Area_Hectares'] = float(area)
    canonical = next((c for c in trained_crops
                      if str(c).strip().lower() == str(crop or '').strip().lower()), None)
    if canonical is not None and f'Crop_{canonical}' in row:
        row[f'Crop_{canonical}'] = 1.0
    elif f'Crop_{crop}' in row:
        row[f'Crop_{crop}'] = 1.0
    return pd.DataFrame([[row[name] for name in columns]], columns=columns)


def get_yield_vqc_model():
    """Variational quantum regressor for the (crop, season, area) contract.

    `train_all_models.py` writes `vqc_yield_model.pkl` on exactly the one-hot
    layout this API builds, so that artifact is loaded first. Older artifacts of
    that name were fitted on a five-feature soil schema (Fertilizer, temp, N, P,
    K) that this API does not accept, so a `SimulatedQuantumRegressor` fitted from
    the yield dataset on the same one-hot layout is used as the fallback. Either
    way the quantum column is a second real model rather than the classical value
    relabelled.
    """
    global _yield_vqc_model
    if _yield_vqc_model is None:
        artifact = load_helper('vqc_yield_model.pkl')
        # The projection matrix is created at fit time with one row per input
        # feature, so its height is the artifact's real feature count.
        projection = getattr(artifact, 'projection_matrix', None)
        if artifact is not None and projection is not None and getattr(projection, 'shape', (None,))[0] == len(yield_feature_columns()):
            _yield_vqc_model = artifact
            print("[YIELD] Loaded models/vqc_yield_model.pkl (active Crop+Area contract)")
            return _yield_vqc_model
        try:
            columns = yield_feature_columns()
            reason = None
            for source in (YIELD_TRAINING_CSV, LEGACY_YIELD_TRAINING_CSV):
                try:
                    df = pd.read_csv(source)
                    break
                except Exception as e:
                    reason = e
                    df = None
            if df is None:
                raise RuntimeError(reason)
            frame = pd.DataFrame({
                'Crop': df['Crop'].astype(str),
                'Area_Hectares': df['Area_Hectares'].astype(float),
            })
            encoded = pd.get_dummies(frame[['Crop']].astype(str), prefix='Crop').reindex(
                columns=columns, fill_value=0.0)
            encoded['Area_Hectares'] = frame['Area_Hectares'].to_numpy(dtype=float)
            encoded = encoded[columns].astype(float)
            target = df['Yield_Tonnes'].to_numpy(dtype=float)
            model = qml_model.SimulatedQuantumRegressor(n_components=8, alpha=0.01, epochs=100)
            model.fit(encoded.to_numpy(dtype=float), target)
            _yield_vqc_model = model
            print(f"[YIELD] VQC regressor fitted from {os.path.relpath(source)} ({len(columns)} columns)")
        except Exception as e:
            print(f"Yield VQC unavailable: {e}")
            _yield_vqc_model = False
    return _yield_vqc_model or None


def run_yield_models(crop, area, season=None):
    """Run both yield models. Returns (classical_t_ha, quantum_t_ha, notes).

    Contract: Crop + Area_Hectares -> Yield_Tonnes (the whole area's harvest), so
    each result is divided by the requested area to give the per-hectare figure
    the app displays. `season` is accepted ONLY for backwards compatibility with
    older clients and is ignored by both models; when it is supplied the notes
    say so explicitly rather than letting it look like a model input.
    """
    model = get_yield_model()
    if model is None:
        return None, None, "Yield model is not available on the server."

    area = float(area) or 1.0
    features = yield_feature_frame(crop, area)
    classical = round(float(model.predict(features)[0]) / area, 2)

    notes = []
    if season not in (None, ''):
        notes.append("`season` is deprecated and ignored: the yield model is trained on "
                     "annual district-level crop statistics and has no season input.")
    trained_crops = get_yield_manifest().get('crop_options') or []
    if trained_crops and not any(str(c).strip().lower() == str(crop or '').strip().lower()
                                 for c in trained_crops):
        notes.append(f"{crop!r} is not among the {len(trained_crops)} crops in the yield "
                     f"training data, so this is the model's crop-independent (area-only) "
                     f"estimate.")

    quantum = None
    vqc = get_yield_vqc_model()
    if vqc is not None:
        try:
            quantum = round(float(vqc.predict(features.to_numpy(dtype=float))[0]) / area, 2)
        except Exception as e:
            notes.append(f"VQC unavailable: {e}")
    else:
        notes.append("VQC unavailable: model could not be prepared on the server.")

    return classical, quantum, "; ".join(notes)


DISTRICT_WEATHER = {
    "Bagalkot": {"temp": 28.5, "hum": 45.0, "rain": 40.0},
    "Ballari": {"temp": 30.2, "hum": 42.0, "rain": 45.0},
    "Belagavi": {"temp": 25.0, "hum": 60.0, "rain": 70.0},
    "Bengaluru Rural": {"temp": 23.5, "hum": 62.0, "rain": 85.0},
    "Bengaluru Urban": {"temp": 24.0, "hum": 65.0, "rain": 90.0},
    "Bidar": {"temp": 27.5, "hum": 50.0, "rain": 55.0},
    "Chamarajanagara": {"temp": 26.0, "hum": 58.0, "rain": 80.0},
    "Chikkaballapur": {"temp": 25.5, "hum": 55.0, "rain": 75.0},
    "Chikkamagaluru": {"temp": 21.0, "hum": 75.0, "rain": 180.0},
    "Chitradurga": {"temp": 27.8, "hum": 48.0, "rain": 50.0},
    "Dakshina Kannada": {"temp": 28.5, "hum": 85.0, "rain": 250.0},
    "Davanagere": {"temp": 26.5, "hum": 52.0, "rain": 60.0},
    "Dharwad": {"temp": 24.0, "hum": 60.0, "rain": 75.0},
    "Gadag": {"temp": 26.5, "hum": 50.0, "rain": 65.0},
    "Hassan": {"temp": 23.0, "hum": 68.0, "rain": 110.0},
    "Haveri": {"temp": 25.5, "hum": 58.0, "rain": 85.0},
    "Kalaburagi": {"temp": 31.0, "hum": 40.0, "rain": 40.0},
    "Kodagu": {"temp": 20.5, "hum": 80.0, "rain": 220.0},
    "Kolar": {"temp": 24.5, "hum": 58.0, "rain": 65.0},
    "Koppal": {"temp": 29.0, "hum": 45.0, "rain": 50.0},
    "Mandya": {"temp": 26.8, "hum": 62.5, "rain": 85.0},
    "Mysuru": {"temp": 25.5, "hum": 65.0, "rain": 95.0},
    "Raichur": {"temp": 32.0, "hum": 38.0, "rain": 35.0},
    "Ramanagara": {"temp": 25.0, "hum": 60.0, "rain": 80.0},
    "Shivamogga": {"temp": 25.5, "hum": 70.0, "rain": 140.0},
    "Tumakuru": {"temp": 26.0, "hum": 55.0, "rain": 70.0},
    "Udupi": {"temp": 28.0, "hum": 82.0, "rain": 280.0},
    "Uttara Kannada": {"temp": 27.5, "hum": 78.0, "rain": 210.0},
    "Vijayanagara": {"temp": 29.5, "hum": 46.0, "rain": 55.0},
    "Vijayapura": {"temp": 30.5, "hum": 42.0, "rain": 45.0},
    "Yadgir": {"temp": 31.5, "hum": 40.0, "rain": 42.0}
}

@app.route('/api/weather/<district>')
def get_district_weather(district):
    """Reference weather for a district.

    The values in DISTRICT_WEATHER are indicative reference figures, NOT
    measurements, and they are not aligned to any model's training rows. When a
    district has no entry this endpoint no longer invents ``25C / 60% / 100mm``
    as if it were a reading: it says the value is unavailable instead.
    """
    key = next((k for k in DISTRICT_WEATHER if k.lower() == str(district).lower()), None)
    if key is None:
        return jsonify({
            'district': district,
            'available': False,
            'temp': None,
            'hum': None,
            'rain': None,
            'source': None,
            'note': (f'No reference weather entry for {district!r}. Values are not '
                     f'estimated or defaulted; supply a verified source to use them.'),
        })
    return jsonify(dict(DISTRICT_WEATHER[key], district=key, available=True,
                        source='indicative reference values (not measurements)',
                        note='Indicative reference figures, not measurements and not '
                             'aligned to any model training row.'))

# ---- Helper: Read Latest Metrics ----
# Registry entries are keyed by artifact file name; these are the four models the
# dashboard surfaces. Everything reported here is read from training_registry.json.
METRIC_MODEL_KEYS = {
    'rf_model.pkl': 'rf',
    'xgb_model.pkl': 'xgb',
    'svm_model.pkl': 'svm',
    'meta_model.pkl': 'meta',
}


def _headline_metric(entry):
    """Extract a headline percentage from a registry entry, or None.

    Supports both registry schemas:
      * structured (current pipeline): metrics = {"train": {...}, "cv": {...}, "test": {...}}
        with a `task` field; classification reports accuracy, regression reports r2.
      * legacy flat schema: metrics = {"Accuracy": "95.00%"} / {"R2_Score": 0.97}.
    Only held-out test numbers are surfaced, never in-sample training numbers.
    """
    mets = entry.get('metrics') or {}
    if not isinstance(mets, dict):
        return None

    test_block = mets.get('test')
    if isinstance(test_block, dict):
        if test_block.get('accuracy') is not None:
            return f"{float(test_block['accuracy']) * 100:.2f}%"
        if test_block.get('r2') is not None:
            return f"{max(float(test_block['r2']) * 100.0, 0.0):.2f}%"
        return None

    if mets.get('Accuracy') is not None:
        return str(mets['Accuracy']).replace('%', '') + '%'
    if mets.get('R2_Score') is not None:
        val = float(mets['R2_Score'])
        return f"{max(val * 100.0, 0.0):.1f}%" if val > 0 else "0%"
    return None


def get_latest_metrics():
    """Reads models performance metrics from the training registry.

    Returns "N/A" for any model with no registry evidence — the previous version
    fell back to hardcoded percentages (rf 92% / xgb 94% / svm 89% / meta 96%),
    which presented fabricated numbers as measured performance.
    """
    metrics = {key: 'N/A' for key in ('rf', 'xgb', 'svm', 'meta')}
    provenance = {key: None for key in metrics}

    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                registry = json.load(f)

            if isinstance(registry, list):
                # Walk newest -> oldest; first hit per model wins.
                for entry in reversed(registry):
                    key = METRIC_MODEL_KEYS.get(entry.get('model_name'))
                    if not key or provenance[key] is not None:
                        continue
                    # A registry entry can describe a run that deliberately did
                    # not write its artifact (e.g. the XGBoost fallback on a host
                    # without libomp). Those numbers describe an estimator that
                    # is not on disk, so they must not surface as the dashboard's
                    # headline metric for that model.
                    if entry.get('artifact_written') is False:
                        continue
                    value = _headline_metric(entry)
                    if value is not None:
                        metrics[key] = value
                        provenance[key] = {
                            'basis': 'held-out test set',
                            'recorded_at': entry.get('timestamp'),
                            'run_id': entry.get('run_id'),
                            'algorithm': entry.get('algorithm'),
                        }
                    if all(provenance.values()):
                        break
        except Exception as e:
            print(f"Error reading registry metrics: {e}")

    available = [k for k, v in provenance.items() if v]
    metrics['source'] = ('training_registry.json' if available else 'unavailable')
    metrics['provenance'] = provenance
    metrics['note'] = (
        'Held-out test metrics recorded by train_all_models.py. '
        '"N/A" means no registry entry exists for that model.'
    )
    return metrics

# ---- Routes ----

@app.route('/')
def index():
    return jsonify({"status": "SeedIQ API is running"}), 200

# ---- MLOps & Experiment Tracking API Endpoints ----
@app.route('/api/experiments', methods=['GET'])
def get_experiments():
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM experiments ORDER BY created_at DESC').fetchall()
            return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e:
        print(f"Experiments catalogue unavailable: {e}")
        return jsonify([])

@app.route('/api/experiments/<exp_id>', methods=['GET'])
def get_experiment_details(exp_id):
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    with get_db() as conn:
        exp = conn.execute('SELECT * FROM experiments WHERE experiment_id = ?', (exp_id,)).fetchone()
        if not exp:
            return jsonify({"error": "Experiment not found"}), 404
        metrics = conn.execute('SELECT * FROM experiment_metrics WHERE experiment_id = ?', (exp_id,)).fetchall()
        trials = conn.execute('SELECT * FROM hyperparameter_trials WHERE experiment_id = ?', (exp_id,)).fetchall()
        return jsonify({
            "experiment": dict(exp),
            "metrics": [dict(m) for m in metrics],
            "trials": [dict(t) for t in trials]
        })

@app.route('/api/model_versions', methods=['GET'])
def get_model_versions():
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM model_versions ORDER BY created_at DESC').fetchall()
            return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e:
        print(f"Model-version catalogue unavailable: {e}")
        return jsonify([])

@app.route('/api/test_runs', methods=['GET'])
def get_test_runs():
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    try:
        with get_db() as conn:
            rows = conn.execute('SELECT * FROM test_runs ORDER BY timestamp DESC').fetchall()
            return jsonify([dict(row) for row in rows])
    except sqlite3.Error as e:
        print(f"Test-run catalogue unavailable: {e}")
        return jsonify([])

@app.route('/api/training_history', methods=['GET'])
def get_training_history():
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    if os.path.exists('training_history.txt'):
        with open('training_history.txt', 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return jsonify({"history": lines[-50:]})
    return jsonify({"history": []})


@app.route('/api/model_metrics', methods=['GET'])
def model_metrics():
    """Latest registry entry for every model artifact, plus a run summary.

    RESTRICTED: model-performance data (held-out test metrics, generalization
    gaps, dataset provenance) is visible only to authenticated administrators.
    Regular users and guests must not see these numbers — on the backend, not
    just in the UI.
    """
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403

    if not os.path.exists(REGISTRY_FILE):
        return jsonify({
            "available": False,
            "note": "training_registry.json does not exist yet; run a retraining first.",
            "models": [],
            "headline": get_latest_metrics(),
        })

    try:
        with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
            registry = json.load(f)
    except Exception as e:
        return jsonify({
            "available": False,
            "note": f"training_registry.json is unreadable: {e}",
            "models": [],
            "headline": get_latest_metrics(),
        })

    if not isinstance(registry, list):
        return jsonify({
            "available": False,
            "note": "training_registry.json is not a list.",
            "models": [],
            "headline": get_latest_metrics(),
        })

    # Newest entry per artifact; entries that describe a run whose artifact was
    # deliberately not written are still shown, but marked.
    latest = {}
    for entry in reversed(registry):
        name = entry.get('model_name')
        if name and name not in latest:
            latest[name] = entry

    models = []
    for name, entry in latest.items():
        metrics = entry.get('metrics') or {}
        models.append({
            "model_name": name,
            "domain": entry.get('domain'),
            "algorithm": entry.get('algorithm'),
            "task": entry.get('task'),
            "timestamp": entry.get('timestamp'),
            "run_id": entry.get('run_id'),
            "train": metrics.get('train'),
            "cv": metrics.get('cv'),
            "test": metrics.get('test'),
            "generalization": entry.get('generalization'),
            "records": entry.get('records'),
            "features_count": entry.get('features_count'),
            "classes": entry.get('classes'),
            "sample_counts": entry.get('sample_counts'),
            "dataset_provenance": entry.get('dataset_provenance'),
            "simulated_quantum": entry.get('simulated_quantum'),
            "artifact_written": entry.get('artifact_written', True),
            "notes": entry.get('notes'),
        })

    gaps = [m["generalization"]["status"] for m in models
            if isinstance(m.get("generalization"), dict) and m["generalization"].get("status")]
    overall = ("high" if "high" in gaps else
               "moderate" if "moderate" in gaps else
               "good" if gaps else "unknown")

    return jsonify({
        "available": True,
        "entry_count": len(registry),
        "last_run_id": registry[-1].get('run_id') if registry else None,
        "last_run_at": registry[-1].get('timestamp') if registry else None,
        "generalization": {"status": overall},
        "headline": get_latest_metrics(),
        "models": models,
    })

@app.route('/api/hyperparameter_trials/<exp_id>', methods=['GET'])
def get_hyperparameter_trials(exp_id):
    if not session.get('user_id'):
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    if not _is_admin_session():
        return jsonify({"status": "error", "message": "Access denied: administrator privileges required."}), 403
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM hyperparameter_trials WHERE experiment_id = ? ORDER BY trial_number ASC', (exp_id,)).fetchall()
        return jsonify([dict(row) for row in rows])

def send_real_email_otp(recipient_email, otp, purpose="registration"):
    sender_email = (os.environ.get("GMAIL_SENDER_EMAIL") or "").strip()
    sender_password = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    
    print("\n-------------------------------------------------------")
    print(f"[OTP_GENERATED] 6-digit OTP code generated.")
    print(f"   Destination: {recipient_email}")
    print(f"   Purpose: {purpose}")
    print(f"   GMAIL_SENDER_EMAIL configured: {'TRUE' if sender_email else 'FALSE'}")
    print(f"   GMAIL_APP_PASSWORD configured: {'TRUE' if sender_password else 'FALSE'}")
    print(f"   Gmail SMTP configuration: {'READY' if (sender_email and sender_password) else 'NOT READY'}")
    
    resend_api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    resend_sender = (os.environ.get("RESEND_SENDER_EMAIL") or os.environ.get("RESEND_FROM_EMAIL") or "onboarding@resend.dev").strip()

    if not resend_api_key and (not sender_email or not sender_password):
        print("   [EMAIL_FAILURE] Neither Resend API key nor Gmail SMTP credentials are configured.")
        print("   -> Set RESEND_API_KEY or GMAIL_SENDER_EMAIL + GMAIL_APP_PASSWORD in environment.")
        print("-------------------------------------------------------\n")
        if app.config.get('TESTING'):
            return True, "Simulated delivery (testing mode)."
        return False, "Unable to send verification email. Email credentials (Resend or Gmail) are not configured on the server."
        
    if purpose == "password_reset":
        subject = "SeedIQ — Password Reset Verification"
        header_title = "SeedIQ"
        header_sub = "Password Reset Verification"
        notice_text = "Do not share this code with anyone. If you did not request a password reset, you can safely ignore this email."
    else:
        subject = "SeedIQ — Verify Your Email"
        header_title = "SeedIQ"
        header_sub = "Email Verification"
        notice_text = "Do not share this code with anyone. If you did not create a SeedIQ account, please disregard this message."
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #030805; color: #f0fdf4; margin: 0; padding: 25px; }}
        .container {{ max-width: 520px; margin: 0 auto; background: #0a140f; border: 1px solid #10b98140; border-radius: 20px; padding: 32px; box-shadow: 0 20px 60px rgba(0,0,0,0.8); }}
        .header {{ text-align: center; margin-bottom: 24px; }}
        .title {{ color: #34d399; font-size: 28px; font-weight: 800; margin: 8px 0 0 0; letter-spacing: -0.5px; }}
        .subtitle {{ color: #9ca3af; font-size: 15px; margin-top: 4px; font-weight: 600; }}
        .otp-box {{ background: #041f13; border: 2px dashed #10b98180; border-radius: 14px; text-align: center; padding: 22px; margin: 24px 0; }}
        .otp-code {{ font-size: 42px; font-weight: 800; letter-spacing: 12px; color: #34d399; font-family: 'Courier New', Courier, monospace; }}
        .expiry {{ font-size: 13px; color: #9ca3af; margin-top: 8px; font-weight: 500; }}
        .footer {{ font-size: 11px; color: #6ee7b760; text-align: center; margin-top: 30px; border-top: 1px solid #ffffff15; padding-top: 18px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <div style="font-size: 32px;">🌱</div>
          <div class="title">{header_title}</div>
          <div class="subtitle">{header_sub}</div>
        </div>
        <p style="font-size: 14px; color: #d1d5db; line-height: 1.6;">
          Your verification code:
        </p>
        <div class="otp-box">
          <div class="otp-code">{otp}</div>
          <div class="expiry">⏱️ This code expires in 10 minutes.</div>
        </div>
        <p style="font-size: 12px; color: #9ca3af; line-height: 1.5;">
          {notice_text}
        </p>
        <div class="footer">
          SeedIQ · Quantum Intelligence for Agriculture
        </div>
      </div>
    </body>
    </html>
    """
    
    text_content = f"""SeedIQ
{header_sub}

Your verification code:
{otp}

This code expires in 10 minutes.

{notice_text}
"""
    
    # 1. Try Resend HTTPS API (100% Free - 3000 emails/mo, zero socket blocks on cloud)
    resend_api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    resend_sender = (os.environ.get("RESEND_SENDER_EMAIL") or os.environ.get("RESEND_FROM_EMAIL") or "onboarding@resend.dev").strip()
    
    if resend_api_key:
        try:
            print(f"   [RESEND_ATTEMPT] Dispatching email via Resend API to {recipient_email}...")
            payload = {
                "from": f"SeedIQ <{resend_sender}>",
                "to": [recipient_email],
                "subject": subject,
                "html": html_content,
                "text": text_content
            }
            resend_resp = requests.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            if resend_resp.status_code in (200, 201, 202):
                print(f"   [RESEND_SUCCESS] Real verification email delivered via Resend to {recipient_email}")
                print("-------------------------------------------------------\n")
                return True, "Verification email successfully delivered to your inbox."
            else:
                err_data = {}
                try:
                    err_data = resend_resp.json()
                except Exception:
                    pass
                err_msg = err_data.get("message") or resend_resp.text
                print(f"   [RESEND_FAILURE] Resend API HTTP error {resend_resp.status_code}: {err_msg}")
                if resend_resp.status_code == 403 and "own email address" in err_msg:
                    last_resend_error = f"Resend Sandbox Notice: In Resend free tier without a custom domain, emails can only be delivered to your registered Resend account email. Error: {err_msg}"
                else:
                    last_resend_error = f"Resend {resend_resp.status_code}: {err_msg}"
        except Exception as e:
            print(f"   [RESEND_FAILURE] Resend API error: {e}. Falling back to standard SMTP...")
            last_resend_error = str(e)
    else:
        last_resend_error = "RESEND_API_KEY is not set on server"

    # 2. Standard SMTP Dispatcher (Ports 465 / 587)
    if not sender_email or not sender_password:
        return False, f"Email delivery failed: {last_resend_error}"

    try:
        print(f"   [SMTP_ATTEMPT] Connecting to smtp.gmail.com...")
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"SeedIQ <{sender_email}>"
        msg['To'] = recipient_email
        
        msg.attach(MIMEText(text_content, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        server = None
        try:
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
            server.ehlo()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        except Exception:
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
            
        print(f"   [SMTP_SUCCESS] Verification email successfully accepted by Gmail for {recipient_email}")
        print("-------------------------------------------------------\n")
        return True, "Verification email successfully delivered to your Gmail inbox."
    except smtplib.SMTPAuthenticationError as e:
        print(f"   [SMTP_FAILURE] SMTPAuthenticationError: {e}")
        print("-------------------------------------------------------\n")
        msg = "Authentication failed with Gmail SMTP server. Check your Gmail App Password."
        if resend_api_key:
            msg += f" (Resend attempt: {last_resend_error})"
        return False, msg
    except Exception as e:
        print(f"   [SMTP_FAILURE] {type(e).__name__}: {e}")
        print("-------------------------------------------------------\n")
        msg = f"Email delivery failed: {type(e).__name__} ({e})"
        if resend_api_key:
            msg += f" | Resend: {last_resend_error}"
        return False, msg

@app.route('/api/diagnostics/smtp', methods=['GET'])
def smtp_diagnostics():
    resend_api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    resend_sender = (os.environ.get("RESEND_SENDER_EMAIL") or "onboarding@resend.dev").strip()
    resend_configured = bool(resend_api_key)
    
    sender_email = (os.environ.get("GMAIL_SENDER_EMAIL") or "").strip()
    sender_password = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    is_email_set = bool(sender_email)
    is_pass_set = bool(sender_password)
    
    if resend_configured:
        masked_resend = resend_api_key[:6] + "..." + resend_api_key[-4:] if len(resend_api_key) > 10 else "***"
        return jsonify({
            "status": "ready",
            "provider": "Resend HTTPS API (Port 443)",
            "resend_configured": True,
            "resend_key_masked": masked_resend,
            "resend_sender": resend_sender,
            "version": "v1.0.3-useragent",
            "message": "Resend API key is configured. Outbound emails will use Resend HTTPS API."
        }), 200
    
    if not is_email_set or not is_pass_set:
        return jsonify({
            "status": "not_configured",
            "gmail_sender_configured": is_email_set,
            "gmail_app_password_configured": is_pass_set,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "tls": True,
            "message": "Gmail SMTP credentials are not configured. Please set GMAIL_SENDER_EMAIL and GMAIL_APP_PASSWORD in C:\\Users\\SUMITH R\\Desktop\\SeedIQ1\\.env"
        }), 200
        
    server = None
    try:
        try:
            # Direct SSL port 465 connection
            server = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10)
            server.ehlo()
            server.login(sender_email, sender_password)
            active_port = 465
        except Exception:
            # Fallback to STARTTLS port 587
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, sender_password)
            active_port = 587
            
        parts = sender_email.split('@')
        masked = (parts[0][:2] + "***@" + parts[1]) if len(parts) == 2 else "***"
        return jsonify({
            "status": "ready",
            "gmail_sender_configured": True,
            "sender_email_masked": masked,
            "gmail_app_password_configured": True,
            "smtp_connection": "connected",
            "smtp_port_used": active_port,
            "tls_handshake": "successful",
            "authentication": "authenticated",
            "message": f"Gmail SMTP is fully configured and operational via port {active_port}."
        }), 200
    except smtplib.SMTPAuthenticationError as e:
        return jsonify({
            "status": "auth_failed",
            "gmail_sender_configured": True,
            "gmail_app_password_configured": True,
            "smtp_connection": "connected",
            "tls_handshake": "successful",
            "authentication": "failed",
            "error_type": "SMTPAuthenticationError",
            "message": "Authentication failed. Ensure you are using a 16-character Google App Password (not your normal password)."
        }), 200
    except Exception as e:
        return jsonify({
            "status": "connection_error",
            "gmail_sender_configured": True,
            "gmail_app_password_configured": True,
            "error_type": type(e).__name__,
            "message": f"SMTP connection error: {type(e).__name__} ({e})"
        }), 200
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass

def validate_password_strength(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not any(c in special_chars for c in password):
        return False, "Password must contain at least one special character."
    return True, ""

# -------------------------------------------------------------
# 1. Sign In / Login (Email + Password)
# -------------------------------------------------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email_or_user = (data.get('email') or data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    
    if not email_or_user or not password:
        return jsonify({"status": "error", "message": "Email and password are required."}), 400

    admin_email = os.environ.get("SEEDIQ_ADMIN_EMAIL", "admin@seediq.ai").strip().lower()
    researcher_email = os.environ.get("SEEDIQ_RESEARCHER_EMAIL", "researcher@quantum.org").strip().lower()

    target_email = email_or_user
    if target_email == 'admin':
        target_email = admin_email
    elif target_email == 'researcher':
        target_email = researcher_email

    # Fast-path for root admin and researcher accounts to eliminate cloud auth latency
    if target_email in [admin_email, researcher_email] or email_or_user in ['admin', 'researcher']:
        try:
            with get_db() as conn:
                u = conn.execute('SELECT * FROM users WHERE email = ? OR username = ?', (target_email, email_or_user)).fetchone()
                if u and check_password_hash(u['password'], password):
                    resolved_role = "Admin" if (target_email == admin_email or email_or_user == 'admin') else "Researcher"
                    session.clear()
                    session['user_id'] = u['id']
                    session['sqlite_user_id'] = u['id']
                    session['username'] = u['username']
                    session['email'] = u['email']
                    session['role'] = resolved_role
                    session['display_name'] = u['display_name'] or u['username']
                    session['is_guest'] = False
                    log_activity("USER_LOGIN", user_id=str(u['id']), details={"email": u['email'], "provider": "local_sqlite"})
                    return jsonify({
                        "status": "success",
                        "message": "Signed in successfully.",
                        "user": {
                            "id": u['id'],
                            "username": u['username'],
                            "email": u['email'],
                            "display_name": u['display_name'] or u['username'],
                            "role": resolved_role,
                            "provider": "local_sqlite"
                        }
                    }), 200
        except Exception as e:
            print(f"[LOGIN] Fast-path notice: {e}")

    # 1. Attempt Supabase Auth Authentication
    sb_success, sb_res = supabase.sign_in(target_email, password)
    if sb_success and "user" in sb_res:
        sb_user = sb_res["user"]
        sb_uid = sb_user.get("id")
        user_email = (sb_user.get("email") or target_email).lower()
        display_name = sb_user.get("user_metadata", {}).get("display_name") or user_email.split("@")[0]
        
        # Server-side role resolution hierarchy
        if user_email == admin_email or email_or_user == 'admin':
            role = "Admin"
        elif user_email == researcher_email or email_or_user == 'researcher':
            role = "Researcher"
        else:
            role = sb_user.get("user_metadata", {}).get("role") or (sb_res.get("profile") or {}).get("role", "Farmer")
            if role not in ['Admin', 'Researcher', 'Farmer']:
                role = "Farmer"

        session.clear()
        session['user_id'] = sb_uid
        session['supabase_user_id'] = sb_uid
        session['username'] = user_email.split('@')[0]
        session['email'] = user_email
        session['role'] = role
        session['display_name'] = display_name
        session['access_token'] = sb_res.get("access_token")
        session['is_guest'] = False

        # Ensure SQLite has a local mirror for legacy query joins
        try:
            with get_db() as conn:
                local_u = conn.execute('SELECT id FROM users WHERE email = ?', (user_email,)).fetchone()
                if local_u:
                    session['sqlite_user_id'] = local_u['id']
                else:
                    conn.execute(
                        'INSERT INTO users (username, password, email, display_name, role, provider) VALUES (?, ?, ?, ?, ?, "supabase")',
                        (user_email.split('@')[0], _hash_password(password), user_email, display_name, role)
                    )
                    conn.commit()
                    new_local = conn.execute('SELECT id FROM users WHERE email = ?', (user_email,)).fetchone()
                    if new_local:
                        session['sqlite_user_id'] = new_local['id']
        except Exception as e:
            print(f"[LOGIN] SQLite sync notice: {e}")

        log_activity("USER_LOGIN", user_id=sb_uid, details={"email": user_email, "provider": "supabase_auth"})

        return jsonify({
            "status": "success",
            "message": "Signed in successfully.",
            "user": {
                "id": sb_uid,
                "username": user_email.split('@')[0],
                "email": user_email,
                "display_name": display_name,
                "role": role,
                "provider": "supabase_auth"
            }
        }), 200

    # 2. Fallback to local SQLite authentication
    with get_db() as conn:
        user = conn.execute(
            'SELECT * FROM users WHERE email = ? OR username = ?', 
            (email_or_user, email_or_user)
        ).fetchone()
        
        if not user or not check_password_hash(user['password'], password):
            log_activity("LOGIN_FAILED", user_id=None, details={"identifier": email_or_user}, status="FAILED")
            return jsonify({"status": "error", "message": "Invalid email or password."}), 401
            
        # Server-side role resolution hierarchy
        if (user['email'] and user['email'].lower() == admin_email) or user['username'] == 'admin' or email_or_user == 'admin':
            role = "Admin"
        elif (user['email'] and user['email'].lower() == researcher_email) or user['username'] == 'researcher' or email_or_user == 'researcher':
            role = "Researcher"
        else:
            role = user['role'] if user['role'] in ['Admin', 'Researcher', 'Farmer'] else "Farmer"
            
        session.clear()
        session['user_id'] = user['id']
        session['sqlite_user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']
        session['role'] = role
        session['display_name'] = user['display_name'] or user['username']
        session['is_guest'] = False

        log_activity("USER_LOGIN", user_id=str(user['id']), details={"email": user['email'], "provider": "local_sqlite"})

        return jsonify({
            "status": "success",
            "message": "Signed in successfully.",
            "user": {
                "id": user['id'],
                "username": user['username'],
                "email": user['email'],
                "display_name": user['display_name'] or user['username'],
                "role": role,
                "provider": "local"
            }
        }), 200


# -------------------------------------------------------------
# 2. Registration Flow (Request OTP -> Verify OTP & Create Account)
# -------------------------------------------------------------
def _get_app_cipher():
    import base64, hashlib
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(app.secret_key.encode()).digest())
    return Fernet(key)

@app.route('/api/register/request-otp', methods=['POST'])
def register_request_otp():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    
    if not name:
        return jsonify({"status": "error", "success": False, "email_sent": False, "message": "Full name is required."}), 400
    if not email or '@' not in email:
        return jsonify({"status": "error", "success": False, "email_sent": False, "message": "Please enter a valid Gmail/email address."}), 400
        
    is_valid, msg = validate_password_strength(password)
    if not is_valid:
        return jsonify({"status": "error", "success": False, "email_sent": False, "message": msg}), 400
        
    now = datetime.datetime.now()
    
    with get_db() as conn:
        # Check if email is already registered locally
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            return jsonify({"status": "error", "success": False, "email_sent": False, "message": "An account with this email address already exists. Please sign in."}), 409
            
        # Rate limit check (20 seconds, skipped in test mode)
        if not app.config.get('TESTING'):
            existing_otp = conn.execute('SELECT created_at FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,)).fetchone()
            if existing_otp and existing_otp['created_at']:
                try:
                    created_dt = datetime.datetime.strptime(existing_otp['created_at'], '%Y-%m-%d %H:%M:%S')
                    elapsed = (now - created_dt).total_seconds()
                    if elapsed < 20:
                        remaining = int(20 - elapsed)
                        return jsonify({
                            "status": "error",
                            "success": False,
                            "email_sent": False,
                            "message": f"Please wait {remaining} seconds before requesting another code.",
                            "retry_after": remaining
                        }), 429
                except Exception:
                    pass
                
        otp = f"{secrets.randbelow(900000) + 100000}"
        expires_at = (now + datetime.timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        # Encrypt password temporarily in otp_codes table
        cipher = _get_app_cipher()
        enc_pw = cipher.encrypt(password.encode()).decode()
        
        conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,))
        conn.execute(
            'INSERT INTO otp_codes (email, otp, purpose, name, password_hash, attempts, created_at, expires_at) VALUES (?, ?, "registration", ?, ?, 0, ?, ?)',
            (email, otp, name, enc_pw, now_str, expires_at)
        )
        conn.commit()
        
    log_activity("OTP_SENT", user_id=None, details={"email": email, "purpose": "registration"})

    # Attempt real email dispatch via SMTP / Resend API
    email_success, email_status_msg = send_real_email_otp(email, otp, purpose="registration")
    
    if not email_success:
        # Clean up database record on failed delivery so the user is not rate-limited on retry
        with get_db() as conn:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,))
            conn.commit()
            
        return jsonify({
            "status": "error",
            "success": False,
            "email_sent": False,
            "message": email_status_msg or "We could not send the verification email. Please try again."
        }), 500
        
    return jsonify({
        "status": "success",
        "success": True,
        "email_sent": True,
        "message": f"Verification code sent to {email}. Please check your Gmail inbox."
    }), 200

@app.route('/api/register/verify-otp', methods=['POST'])
def register_verify_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    otp = (data.get('otp') or '').strip()
    
    if not email or not otp:
        return jsonify({"status": "error", "message": "Email and verification code are required."}), 400
        
    with get_db() as conn:
        record = conn.execute(
            'SELECT * FROM otp_codes WHERE email = ? AND purpose = "registration"',
            (email,)
        ).fetchone()
        
        if not record:
            return jsonify({"status": "error", "message": "No pending registration found for this email. Please submit the form again."}), 400
            
        attempts = record['attempts'] if 'attempts' in record.keys() else 0
        if attempts >= 5:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Too many attempts. Please request a new code."}), 400
            
        stored_otp = str(record['otp']).strip()
        provided_otp = str(otp).strip()
        print(f"[OTP_VERIFY] Checking email: {email} | Provided: '{provided_otp}' | Stored: '{stored_otp}'")
        
        if stored_otp != provided_otp:
            conn.execute('UPDATE otp_codes SET attempts = attempts + 1 WHERE email = ? AND purpose = "registration"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Verification code is incorrect."}), 400
            
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if record['expires_at'] < now_str:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Verification code has expired. Please request a new code."}), 400
            
        name = record['name'] or email.split('@')[0]
        enc_pw = record['password_hash']
        username = email.split('@')[0]
        
        # Burn registration OTP immediately
        conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,))
        conn.commit()

        # Decrypt password
        raw_pw = ""
        try:
            cipher = _get_app_cipher()
            raw_pw = cipher.decrypt(enc_pw.encode()).decode()
        except Exception as e:
            print(f"[OTP_VERIFY] Password decryption note: {e}")

        # 1. Register in Supabase Auth
        sb_uid = None
        if raw_pw:
            ok, sb_res = supabase.sign_up(email=email, password=raw_pw, display_name=name, role="Farmer")
            if ok and sb_res:
                sb_uid = sb_res.get("id") or (sb_res.get("user") or {}).get("id")

        # 2. Local SQLite record for fallback
        local_hash = _hash_password(raw_pw) if raw_pw else enc_pw
        try:
            conn.execute(
                'INSERT INTO users (username, password, email, display_name, role, provider) VALUES (?, ?, ?, ?, "Farmer", ?)',
                (username, local_hash, email, name, "supabase_auth" if sb_uid else "local")
            )
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        except sqlite3.IntegrityError:
            unique_u = f"{username}_{secrets.randbelow(900) + 100}"
            conn.execute(
                'INSERT INTO users (username, password, email, display_name, role, provider) VALUES (?, ?, ?, ?, "Farmer", ?)',
                (unique_u, local_hash, email, name, "supabase_auth" if sb_uid else "local")
            )
            conn.commit()
            user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            
        target_uid = sb_uid or user['id']
        session.clear()
        session['user_id'] = target_uid
        session['supabase_user_id'] = sb_uid
        session['sqlite_user_id'] = user['id']
        session['username'] = user['username']
        session['email'] = user['email']
        session['role'] = "Farmer"
        session['display_name'] = user['display_name'] or user['username']
        session['is_guest'] = False

        log_activity("USER_REGISTERED", user_id=str(target_uid), details={"email": email, "role": "Farmer"})
        log_activity("OTP_VERIFIED", user_id=str(target_uid), details={"email": email, "purpose": "registration"})
        
        return jsonify({
            "status": "success",
            "message": "Account created successfully.",
            "user": {
                "id": target_uid,
                "username": user['username'],
                "email": user['email'],
                "display_name": user['display_name'],
                "role": "Farmer",
                "provider": "supabase_auth" if sb_uid else "local"
            }
        }), 201


# -------------------------------------------------------------
# 3. Forgot Password Flow (Request OTP -> Verify OTP -> Reset Password)
# -------------------------------------------------------------
@app.route('/api/forgot-password/request-otp', methods=['POST'])
def forgot_password_request_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    
    if not email or '@' not in email:
        return jsonify({"status": "error", "message": "Please enter a valid Gmail/email address."}), 400
        
    with get_db() as conn:
        user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if not user:
            return jsonify({"status": "error", "message": "No account found with this email address."}), 404
            
        now = datetime.datetime.now()
        # Rate limit check (skipped in test mode)
        if not app.config.get('TESTING'):
            existing_otp = conn.execute('SELECT created_at FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,)).fetchone()
            if existing_otp and existing_otp['created_at']:
                try:
                    created_dt = datetime.datetime.strptime(existing_otp['created_at'], '%Y-%m-%d %H:%M:%S')
                    elapsed = (now - created_dt).total_seconds()
                    if elapsed < 20:
                        remaining = int(20 - elapsed)
                        return jsonify({
                            "status": "error",
                            "success": False,
                            "email_sent": False,
                            "message": f"Please wait {remaining} seconds before requesting another code.",
                            "retry_after": remaining
                        }), 429
                except Exception:
                    pass
                    
        otp = f"{secrets.randbelow(900000) + 100000}"
        expires_at = (now + datetime.timedelta(minutes=10)).strftime('%Y-%m-%d %H:%M:%S')
        now_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,))
        conn.execute(
            'INSERT INTO otp_codes (email, otp, purpose, attempts, created_at, expires_at) VALUES (?, ?, "password_reset", 0, ?, ?)',
            (email, otp, now_str, expires_at)
        )
        conn.commit()
        
    # Attempt real email dispatch via SMTP
    email_success, email_status_msg = send_real_email_otp(email, otp, purpose="password_reset")
    
    if not email_success:
        with get_db() as conn:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,))
            conn.commit()
            
        return jsonify({
            "status": "error",
            "success": False,
            "email_sent": False,
            "message": email_status_msg or "We could not send the verification email. Please try again."
        }), 500
        
    return jsonify({
        "status": "success",
        "success": True,
        "email_sent": True,
        "message": f"Password reset code sent to {email}. Check your Gmail inbox."
    }), 200

@app.route('/api/forgot-password/verify-otp', methods=['POST'])
def forgot_password_verify_otp():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    otp = (data.get('otp') or '').strip()
    
    if not email or not otp:
        return jsonify({"status": "error", "message": "Email and verification code are required."}), 400
        
    with get_db() as conn:
        record = conn.execute(
            'SELECT * FROM otp_codes WHERE email = ? AND purpose = "password_reset"',
            (email,)
        ).fetchone()
        
        if not record:
            return jsonify({"status": "error", "message": "No password reset request found. Please request a new code."}), 400
            
        attempts = record['attempts'] if 'attempts' in record.keys() else 0
        if attempts >= 5:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Too many attempts. Please request a new code."}), 400
            
        if record['otp'] != otp:
            conn.execute('UPDATE otp_codes SET attempts = attempts + 1 WHERE email = ? AND purpose = "password_reset"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Verification code is incorrect."}), 400
            
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if record['expires_at'] < now_str:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Verification code has expired. Please request a new code."}), 400
            
        return jsonify({
            "status": "success",
            "message": "Identity verified successfully."
        }), 200

@app.route('/api/forgot-password/reset-password', methods=['POST'])
@app.route('/api/forgot-password/reset', methods=['POST'])
def forgot_password_reset_password():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    otp = (data.get('otp') or '').strip()
    new_password = data.get('new_password') or data.get('newPassword') or data.get('password') or ''
    
    if not email or not otp or not new_password:
        return jsonify({"status": "error", "message": "Email, verification code, and new password are required."}), 400
        
    is_valid, msg = validate_password_strength(new_password)
    if not is_valid:
        return jsonify({"status": "error", "message": msg}), 400
        
    with get_db() as conn:
        record = conn.execute(
            'SELECT * FROM otp_codes WHERE email = ? AND purpose = "password_reset"',
            (email,)
        ).fetchone()
        
        if not record or record['otp'] != otp:
            return jsonify({"status": "error", "message": "Invalid or expired verification session. Please restart recovery."}), 400
            
        now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if record['expires_at'] < now_str:
            conn.execute('DELETE FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,))
            conn.commit()
            return jsonify({"status": "error", "message": "Verification code has expired."}), 400
            
        # Invalidate OTP code
        conn.execute('DELETE FROM otp_codes WHERE email = ?', (email,))
        
        # Update user password securely in SQLite
        new_hash = _hash_password(new_password)
        try:
            conn.execute(
                'UPDATE users SET password = ?, updated_at = CURRENT_TIMESTAMP WHERE email = ?',
                (new_hash, email)
            )
        except Exception:
            conn.execute(
                'UPDATE users SET password = ? WHERE email = ?',
                (new_hash, email)
            )
        conn.commit()

        # Update Supabase password if session token exists
        token = session.get('access_token')
        if token:
            supabase.update_password(token, new_password)
        
        user_id = session.get('user_id') or email
        log_activity("PASSWORD_CHANGED", user_id=str(user_id), details={"email": email})
        
    return jsonify({
        "status": "success",
        "message": "Your password has been updated successfully. Please sign in."
    }), 200


# -------------------------------------------------------------
# 4. Guest Mode & Session Routes
# -------------------------------------------------------------
@app.route('/api/guest-login', methods=['POST'])
def guest_login():
    session.clear()
    session['user_id'] = None
    session['username'] = 'guest_preview'
    session['display_name'] = 'Guest Preview'
    session['role'] = 'Guest'
    session['is_guest'] = True
    
    return jsonify({
        "status": "success",
        "user": {
            "id": "guest",
            "username": "guest_preview",
            "email": "guest@seediq.local",
            "display_name": "Guest Preview",
            "role": "Guest",
            "isGuest": True,
            "provider": "guest"
        }
    }), 200

@app.route('/api/me', methods=['GET'])
def get_current_user():
    if session.get('is_guest'):
        return jsonify({
            "authenticated": True,
            "user": {
                "id": "guest",
                "username": "guest_preview",
                "email": "guest@seediq.local",
                "display_name": "Guest Preview",
                "role": "Guest",
                "isGuest": True,
                "provider": "guest"
            }
        }), 200

    user_id = session.get('user_id')
    sqlite_uid = session.get('sqlite_user_id')
    email = session.get('email')
    username = session.get('username')
    session_role = session.get('role')
    display_name = session.get('display_name')

    if not user_id and not email:
        return jsonify({"authenticated": False}), 200

    admin_email = os.environ.get("SEEDIQ_ADMIN_EMAIL", "admin@seediq.ai").strip().lower()
    researcher_email = os.environ.get("SEEDIQ_RESEARCHER_EMAIL", "researcher@quantum.org").strip().lower()

    with get_db() as conn:
        user = None
        if sqlite_uid:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (sqlite_uid,)).fetchone()
        elif isinstance(user_id, int):
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user and email:
            user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if not user and username:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user:
            role = user['role'] if user['role'] in ['Admin', 'Researcher', 'Farmer'] else "Farmer"
            if (user['email'] and user['email'].lower() == admin_email) or user['username'] == 'admin':
                role = "Admin"
            elif (user['email'] and user['email'].lower() == researcher_email) or user['username'] == 'researcher':
                role = "Researcher"
            elif session.get('phone') and user['id'] == session.get('sqlite_user_id'):
                role = session_role or role
            return jsonify({
                "authenticated": True,
                "user": {
                    "id": user['id'],
                    "username": user['username'],
                    "email": user['email'],
                    "phone": (user['phone'] if 'phone' in user.keys() else None) or session.get('phone'),
                    "display_name": user['display_name'] or user['username'],
                    "role": role,
                    "provider": user['provider']
                }
            }), 200

    if email or user_id:
        role = session_role or "Farmer"
        if (email and email.lower() == admin_email) or username == 'admin':
            role = "Admin"
        elif (email and email.lower() == researcher_email) or username == 'researcher':
            role = "Researcher"
        return jsonify({
            "authenticated": True,
            "user": {
                "id": user_id or 1,
                "username": username or (email.split('@')[0] if email else "user"),
                "email": email,
                "phone": session.get('phone'),
                "display_name": display_name or username or "User",
                "role": role,
                "provider": session.get('auth_provider') or "supabase_auth"
            }
        }), 200

    return jsonify({"authenticated": False}), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    uid = session.get('user_id')
    if uid:
        log_activity("USER_LOGOUT", user_id=str(uid))
    session.clear()
    resp = jsonify({"status": "success", "message": "Logged out successfully"})
    resp.delete_cookie(app.config.get('SESSION_COOKIE_NAME', 'session'))
    return resp, 200


# Legacy compatibility route if needed
@app.route('/api/send-otp', methods=['POST'])
def send_otp_legacy():
    return register_request_otp()

@app.route('/api/verify-otp', methods=['POST'])
def verify_otp_legacy():
    return register_verify_otp()

@app.route('/api/retrain', methods=['POST'])
def retrain_models():
    if session.get('role') != 'Admin':
        return jsonify({"status": "error", "message": "Access Denied: Administrator privileges required to trigger model retraining."}), 403
        
    try:
        import subprocess
        import sys as _sys

        base_dir = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(base_dir, 'reports', 'retrain_report.json')
        # Never serve a stale report if this run dies before writing one.
        try:
            if os.path.exists(report_path):
                os.remove(report_path)
        except OSError as e:
            print(f"Could not clear previous retrain report: {e}")

        result = subprocess.run(
            [_sys.executable, 'train_all_models.py', '--report', report_path],
            capture_output=True, text=True, timeout=240, cwd=base_dir,
        )

        report = None
        if os.path.exists(report_path):
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    report = json.load(f)
            except Exception as e:
                print(f"Retrain report unreadable: {e}")

        return jsonify({
            "status": "success" if result.returncode == 0 else "error",
            "output": result.stdout[-20000:],
            "error": result.stderr[-4000:],
            "report": report,
        }), 200 if result.returncode == 0 else 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/database', methods=['GET', 'POST'])
def database():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    if not session.get('role') or session.get('role').lower() != 'admin':
        flash('Access Denied: Administrative privileges required.', 'error')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'seed_sample':
            sample_predictions = [
                ('crop', 
                 {'nitrogen': 90, 'phosphorus': 42, 'potassium': 43, 'temperature': 20.87, 'humidity': 82.0, 'ph': 6.5, 'rainfall': 202.93},
                 {'classical': 'Rice', 'quantum': 'Rice', 'ensemble': 'Rice'}),
                ('crop', 
                 {'nitrogen': 60, 'phosphorus': 55, 'potassium': 30, 'temperature': 25.6, 'humidity': 71.2, 'ph': 7.2, 'rainfall': 150.5},
                 {'classical': 'Maize', 'quantum': 'Maize', 'ensemble': 'Maize'}),
                ('crop', 
                 {'nitrogen': 40, 'phosphorus': 30, 'potassium': 65, 'temperature': 18.2, 'humidity': 55.4, 'ph': 6.2, 'rainfall': 80.0},
                 {'classical': 'Wheat', 'quantum': 'Wheat', 'ensemble': 'Wheat'}),
                ('yield',
                 {'crop': 'Rice', 'season': 'Kharif', 'area': 5.0},
                 {'classical': 18.5, 'quantum': 17.8, 'ensemble': 18.15}),
                ('yield',
                 {'crop': 'Wheat', 'season': 'Rabi', 'area': 4.0},
                 {'classical': 12.4, 'quantum': 12.0, 'ensemble': 12.2}),
                ('yield',
                 {'crop': 'Maize', 'season': 'Summer', 'area': 2.5},
                 {'classical': 8.2, 'quantum': 8.5, 'ensemble': 8.35}),
                ('seed',
                 {'moisture': 9.5, 'weight': 56.4},
                 {'classical': 'Viable', 'quantum': 'Viable', 'ensemble': 'Viable'}),
                ('seed',
                 {'moisture': 14.8, 'weight': 38.2},
                 {'classical': 'Non-Viable', 'quantum': 'Non-Viable', 'ensemble': 'Non-Viable'}),
                ('seed',
                 {'moisture': 10.8, 'weight': 52.0},
                 {'classical': 'Viable', 'quantum': 'Viable', 'ensemble': 'Viable'}),
                ('quantum',
                 {'nitrogen': 90, 'phosphorus': 42, 'potassium': 43, 'ph': 6.5, 'crop': 'Rice', 'season': 'Kharif', 'area': 5.0},
                 {'crop_rf': 'Rice', 'crop_vqc': 'Rice', 'yield_xgb': 18.5, 'yield_vqr': 17.8, 'seed_svm': 'Viable', 'seed_vqc': 'Viable', 'prob_success': 94.2, 'decision': 'Optimal Performance'}),
                ('quantum',
                 {'nitrogen': 40, 'phosphorus': 30, 'potassium': 65, 'ph': 6.2, 'crop': 'Wheat', 'season': 'Rabi', 'area': 4.0},
                 {'crop_rf': 'Wheat', 'crop_vqc': 'Wheat', 'yield_xgb': 12.4, 'yield_vqr': 12.0, 'seed_svm': 'Viable', 'seed_vqc': 'Viable', 'prob_success': 87.9, 'decision': 'Optimal Performance'})
            ]
            # These rows are DEMO rows, not output of a trained model. They are tagged
            # so an example score (e.g. "94.2% Optimal Performance") can never be read
            # from the ledger as a real prediction.
            with get_db() as conn:
                for p_type, inputs, results in sample_predictions:
                    marked_results = dict(results)
                    marked_results['_sample'] = True
                    marked_results['_note'] = ('seeded demo row — not produced by a trained '
                                               'model; do not read as a measured prediction')
                    conn.execute('''
                        INSERT INTO predictions (user_id, prediction_type, inputs, results)
                        VALUES (?, ?, ?, ?)
                    ''', (session['user_id'], p_type, json.dumps(inputs), json.dumps(marked_results)))
                conn.commit()
            flash('Seeded clearly-marked DEMO rows (not model predictions).', 'success')
        elif action == 'clear_logs':
            with get_db() as conn:
                conn.execute('DELETE FROM predictions WHERE user_id = ?', (session['user_id'],))
                conn.commit()
            flash('Telemetry predictions ledger successfully cleared.', 'success')
        return redirect(url_for('database'))
        
    users_list = []
    predictions_list = []
    try:
        with get_db() as conn:
            users_rows = conn.execute('SELECT id, username, role FROM users ORDER BY id ASC').fetchall()
            for r in users_rows:
                users_list.append({'id': r['id'], 'username': r['username'], 'role': r['role']})
            pred_rows = conn.execute('''
                SELECT id, user_id, prediction_type, inputs, results, timestamp 
                FROM predictions 
                WHERE user_id = ?
                ORDER BY timestamp DESC
            ''', (session['user_id'],)).fetchall()
            for r in pred_rows:
                predictions_list.append({
                    'id': r['id'],
                    'prediction_type': r['prediction_type'],
                    'inputs': json.loads(r['inputs']),
                    'results': json.loads(r['results']),
                    'timestamp': r['timestamp']
                })
    except Exception as e:
        print(f"Error loading database details: {e}")
    return jsonify({"users": users_list, "predictions": predictions_list})

@app.route('/api/dashboard')
def dashboard():
    # Model-performance metrics are admin-only. Guests and regular users get a
    # placeholder so the Home screen can still render the rest of the dashboard
    # without leaking held-out test numbers.
    is_admin = _is_admin_session()
    metrics = get_latest_metrics() if is_admin else None

    if session.get('is_guest'):
        return jsonify({
            "username": "Guest Preview",
            "metrics": metrics,
            "history": [],
            "total_runs": 0,
            "avg_yield": 0.0,
            "viability_rate": 0.0,
            "top_crop": "None"
        }), 200
        
    user_id = session.get('user_id')
    if not user_id:
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return redirect(url_for('login'))
    
    # Query prediction statistics and history
    history = []
    total_runs = 0
    avg_yield = 0.0
    viability_rate = 0.0
    top_crop = "None"
    
    try:
        with get_db() as conn:
            # Get latest 10 predictions for log
            rows = conn.execute('''
                SELECT prediction_type, inputs, results, timestamp 
                FROM predictions 
                WHERE user_id = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (session['user_id'],)).fetchall()
            
            for row in rows:
                history.append({
                    'type': row['prediction_type'],
                    'inputs': json.loads(row['inputs']),
                    'results': json.loads(row['results']),
                    'timestamp': row['timestamp']
                })
                
            # Compute stats
            total_runs = conn.execute('SELECT COUNT(*) FROM predictions WHERE user_id = ?', (session['user_id'],)).fetchone()[0]
            
            # Avg yield
            yields = conn.execute("SELECT results FROM predictions WHERE user_id = ? AND prediction_type = 'yield'", (session['user_id'],)).fetchall()
            if yields:
                sum_yield = sum(json.loads(y['results']).get('ensemble', 0.0) for y in yields)
                avg_yield = round(sum_yield / len(yields), 1)
                
            # Viability rate
            seeds = conn.execute("SELECT results FROM predictions WHERE user_id = ? AND prediction_type = 'seed'", (session['user_id'],)).fetchall()
            if seeds:
                viable_count = sum(1 for s in seeds if json.loads(s['results']).get('ensemble') == 'Viable')
                viability_rate = round((viable_count / len(seeds)) * 100, 1)
                
            # Top crop choice
            crops = conn.execute("SELECT results FROM predictions WHERE user_id = ? AND prediction_type = 'crop'", (session['user_id'],)).fetchall()
            if crops:
                crop_names = [json.loads(c['results']).get('ensemble') for c in crops]
                if crop_names:
                    from collections import Counter
                    top_crop = Counter(crop_names).most_common(1)[0][0]
    except Exception as e:
        print(f"Error loading dashboard stats: {e}")
        
    return jsonify({
        "username": session.get('username'),
        "metrics": metrics,
        "history": history,
        "total_runs": total_runs,
        "avg_yield": avg_yield,
        "viability_rate": viability_rate,
        "top_crop": top_crop
    })

@app.route('/api/datasets', methods=['GET'])
def get_datasets():
    """
    Returns catalogue of uploaded and versioned datasets for the database console (_app.database.tsx).
    """
    datasets_list = []
    
    # 1. Try to query Supabase datasets & dataset_versions
    try:
        ok, rows = supabase.select_rows("dataset_versions", "select=id,dataset_name,version,row_count,stored_path,created_at&order=created_at.desc&limit=50")
        if ok and rows:
            for r in rows:
                datasets_list.append({
                    "id": f"DS-{r.get('id', 1000):04d}" if isinstance(r.get('id'), int) else str(r.get('id')),
                    "name": r.get('stored_path', '').split('/')[-1] or f"{r.get('dataset_name')}_{r.get('version')}.csv",
                    "rows": f"{r.get('row_count', 0):,}",
                    "size": "Processed",
                    "date": str(r.get('created_at', ''))[:10] if r.get('created_at') else "Recently",
                    "status": "Ready for Training",
                    "type": r.get('dataset_name', 'Custom Dataset')
                })
    except Exception as e:
        print(f"[API_DATASETS] Supabase fetch notice: {e}")

    # 2. Fallback to local SQLite dataset_versions
    if not datasets_list:
        try:
            with get_db() as conn:
                rows = conn.execute("SELECT * FROM dataset_versions ORDER BY created_at DESC").fetchall()
                for r in rows:
                    datasets_list.append({
                        "id": f"DS-{r['id']:04d}",
                        "name": f"{r['dataset_name']}_{r['version']}.csv",
                        "rows": f"{r['row_count']:,}",
                        "size": "Processed",
                        "date": str(r['created_at'])[:10] if r['created_at'] else "Recently",
                        "status": "Ready for Training",
                        "type": r['dataset_name']
                    })
        except Exception:
            pass

    # 3. Baseline datasets: scan the actual training datasets on disk. This used
    #    to be a hard-coded table whose row counts (2,200 / 10,500 / 1,000) and
    #    file sizes (150 KB / 280 KB) matched no file in data/, so the UI showed
    #    invented dataset statistics and a dataset name the pipeline never reads.
    if not datasets_list:
        try:
            from data_preprocessing import discover_and_route_datasets
            routed = discover_and_route_datasets('data')
            domain_labels = {
                'crop': 'Crop Recommendation',
                'yield': 'Yield Prediction',
                'seed': 'Seed Viability',
            }
            for idx, domain in enumerate(('crop', 'yield', 'seed'), start=1):
                path = routed.get(domain)
                if not path or not os.path.exists(path):
                    continue
                st = os.stat(path)
                try:
                    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                        row_count = max(sum(1 for _ in fh) - 1, 0)
                except OSError:
                    row_count = 0
                datasets_list.append({
                    "id": f"DS-{idx:04d}",
                    "name": os.path.basename(path),
                    "rows": f"{row_count:,}",
                    "size": f"{st.st_size // 1024} KB" if st.st_size < 1024 * 1024
                            else f"{st.st_size / (1024 * 1024):.1f} MB",
                    "date": datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d'),
                    "status": "Active",
                    "type": domain_labels.get(domain, 'Dataset'),
                    "path": path,
                })
        except Exception as e:
            print(f"[API_DATASETS] local dataset scan failed: {e}")

    return jsonify(datasets_list), 200

@app.route('/api/datasets/upload', methods=['GET', 'POST'])
def upload_dataset():
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Researcher']:
        return jsonify({"status": "error", "message": "Access Denied: Admin or Researcher privileges required to upload datasets."}), 403
        
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded."}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file."}), 400
        if not file.filename.lower().endswith('.csv'):
            return jsonify({"status": "error", "message": "Invalid file format. Only CSV files are supported."}), 400

        filename = secure_filename(file.filename)
        MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # Strict 10 MB limit
        file_bytes = file.read()

        # Strict 10MB file size limit check
        if len(file_bytes) > MAX_UPLOAD_SIZE:
            return jsonify({"status": "error", "message": "File size must be 10 MB or less."}), 400

        user_id = session.get('supabase_user_id') or str(session.get('user_id'))
        user_role = session.get('role', 'Admin')
        auth_token = session.get('access_token')

        res = process_and_store_dataset(
            file_input=file_bytes,
            filename=filename,
            user_id=user_id,
            user_role=user_role,
            auth_token=auth_token,
            max_file_size=MAX_UPLOAD_SIZE
        )

        if res.get("status") == "error":
            return jsonify(res), 400

        return jsonify({
            "status": "success",
            "message": res.get("message", "Dataset uploaded and processed successfully."),
            "filename": filename,
            "detected_type": res.get("detected_type"),
            "version": res.get("version"),
            "rows": res.get("rows"),
            "columns": res.get("columns"),
            "original_storage_path": res.get("original_storage_path"),
            "processed_storage_path": res.get("processed_storage_path")
        }), 200
            
    return jsonify({"status": "success", "message": "Upload endpoint ready"}), 200


# ---------------------------------------------------------------------------
# REQUEST INPUT VALIDATION
# ---------------------------------------------------------------------------
# Every numeric field the ML endpoints accept arrives as untrusted client JSON
# (or form data). Without these guards, a null or non-numeric value reached
# float() and produced an unhandled ValueError -> an HTML 500 page, which the
# mobile client cannot parse or explain to the user. These helpers turn that
# class of input into a clean JSON 400 whose message the app can display.


def _json_error(message, status=400):
    """Uniform JSON error envelope for bad client input (never an HTML page)."""
    return jsonify({"status": "error", "message": message}), status


def _coerce_number(raw, field, *, default=None, positive=False):
    """Coerce an untrusted request field to a finite float.

    Raises ValueError with a user-facing message for input the models cannot
    consume: null/blank, non-numeric, NaN/Infinity, or <= 0 when `positive`.
    When the field is null/blank and `default` is given, the default is returned
    instead of raising (this keeps the endpoints' existing optional-field
    behaviour for clients that simply omit a value).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if default is not None:
            return float(default)
        raise ValueError(f"`{field}` is required and must be a number.")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"`{field}` must be a number (received {raw!r}).")
    if not np.isfinite(value):
        raise ValueError(f"`{field}` must be a finite number (received {raw!r}).")
    if positive and value <= 0:
        raise ValueError(f"`{field}` must be greater than 0 (received {raw!r}).")
    return value


def _json_body_or_form():
    """Return the request payload as a mapping, or None when JSON is invalid."""
    if request.is_json:
        return request.get_json(silent=True)
    return request.form


@app.route('/api/crop-recommendation', methods=['GET', 'POST'])
def crop_recommendation():
    user_id = session.get('user_id') if not session.get('is_guest') else None
        
    result = None
    soil_analysis = None
    growth_plan = None
    disease_advisory = None
    
    if request.method == 'POST':
        req_data = _json_body_or_form()
        if req_data is None:
            return _json_error("Request body must be valid JSON.")
        try:
            n = _coerce_number(req_data.get('nitrogen'), 'nitrogen', default=0)
            p = _coerce_number(req_data.get('phosphorus'), 'phosphorus', default=0)
            k = _coerce_number(req_data.get('potassium'), 'potassium', default=0)
            temp = _coerce_number(req_data.get('temperature'), 'temperature', default=0)
            hum = _coerce_number(req_data.get('humidity'), 'humidity', default=0)
            ph = _coerce_number(req_data.get('ph'), 'ph', default=0)
            rain = _coerce_number(req_data.get('rainfall'), 'rainfall', default=0)
        except ValueError as exc:
            return _json_error(str(exc))
        
        if n == 0 and p == 0 and k == 0 and temp == 0 and hum == 0 and ph == 0 and rain == 0:
            result = {"error": "Invalid Soil Parameters. Please enter valid agricultural values."}
            return jsonify(result), 400
        
        # Reload models dynamically if they were not loaded previously
        global rf_model, crop_scaler, crop_encoder, vqc_crop_model
        if not rf_model: rf_model = load_helper('rf_model.pkl')
        if not crop_scaler: crop_scaler = load_helper('crop_scaler.pkl')
        crop_enc = get_crop_encoder()
        if not vqc_crop_model: vqc_crop_model = load_helper('vqc_crop_model.pkl')
        
        if rf_model and crop_scaler and crop_enc:
            try:
                features = pd.DataFrame([[n, p, k, temp, hum, ph, rain]], 
                                        columns=['Nitrogen', 'Phosphorus', 'Potassium', 'Temperature', 'Humidity', 'pH', 'Rainfall'])
                scaled_features = crop_scaler.transform(features)
                
                # Classical
                pred_rf_int = rf_model.predict(scaled_features)[0]
                pred_rf = decode_crop_name(crop_enc, pred_rf_int)
                
                # Quantum
                if vqc_crop_model:
                    pred_qml_int = vqc_crop_model.predict(scaled_features)[0]
                    pred_qml = decode_crop_name(crop_enc, pred_qml_int)
                else:
                    pred_qml = pred_rf
                
                # Ensemble (Consensus Voting)
                ensemble = pred_rf
                
                result = {
                    'classical': pred_rf,
                    'quantum': pred_qml,
                    'ensemble': ensemble
                }
            except Exception as e:
                print(f"Crop prediction runtime error: {e}")
                # Explicitly marked as NOT a model prediction; the rule engine
                # below is a rule of thumb, not inference output.
                val = rule_based_crop(temp, hum, rain, ph)
                result = {
                    'classical': val,
                    'quantum': None,
                    'ensemble': val,
                    'fallback': 'rule-based',
                    'notes': f'Model error: {e}',
                }
        else:
            # Fallback simple rule engine (models could not be loaded)
            val = rule_based_crop(temp, hum, rain, ph)
            result = {
                'classical': val,
                'quantum': None,
                'ensemble': val,
                'fallback': 'rule-based',
                'notes': 'Classical/quantum models are unavailable on the server; '
                         'this is a rule-of-thumb estimate, not a model prediction.'
            }
            
        # Determine Soil Health & Fertilizer advice dynamically from soil_health.json if available
        soil_db = {}
        soil_db_path = os.path.join('knowledge_base', 'soil_health.json')
        if os.path.exists(soil_db_path):
            try:
                with open(soil_db_path, 'r', encoding='utf-8') as f:
                    soil_db = json.load(f)
            except Exception as e:
                print(f"Error reading soil_health.json: {e}")
                
        n_status = "Low" if n < 50 else ("Medium" if n <= 90 else "High")
        n_info = soil_db.get("Nitrogen", {}).get(n_status, {
            "status": "Nitrogen Deficient", 
            "advice": "Apply 50 kg/acre of Urea or compost manure to boost organic nitrogen levels."
        })
        
        p_status = "Low" if p < 40 else ("Medium" if p <= 70 else "High")
        p_info = soil_db.get("Phosphorus", {}).get(p_status, {
            "status": "Phosphorus Deficient",
            "advice": "Apply Single Super Phosphate (SSP) or Bone meal to improve root network."
        })
        
        k_status = "Low" if k < 35 else ("Medium" if k <= 60 else "High")
        k_info = soil_db.get("Potassium", {}).get(k_status, {
            "status": "Potassium Deficient",
            "advice": "Apply Muriate of Potash (MOP) to improve crop disease resilience."
        })
        
        ph_status = "Acidic" if ph < 6.0 else ("Neutral" if ph <= 7.5 else "Alkaline")
        ph_info = soil_db.get("pH", {}).get(ph_status, {
            "status": "Acidic Soil (pH < 6.0)",
            "advice": "Add Agricultural Lime (Calcium Carbonate) to neutralize soil acidity."
        })
        
        soil_analysis = {
            'nitrogen': {'status': n_info.get('status', n_status), 'advice': n_info.get('advice', '')},
            'phosphorus': {'status': p_info.get('status', p_status), 'advice': p_info.get('advice', '')},
            'potassium': {'status': k_info.get('status', k_status), 'advice': k_info.get('advice', '')},
            'ph': {'status': ph_info.get('status', ph_status), 'advice': ph_info.get('advice', '')}
        }
        
        # Crop specific growth plan
        # `result` may be an error/fallback payload when the models fail; do not
        # index it blindly (that used to raise KeyError -> HTTP 500).
        crop_name = result.get('ensemble') or result.get('classical')
        growth_plan = None
        knowledge_crop = crop_name

        # Load from knowledge_base/growth_planner.json if available.
        # The knowledge base is Title-cased ('Rice') while the trained encoder
        # emits the dataset labels ('rice'), so the lookup must be case
        # insensitive — a direct dict lookup silently produced the 1-step
        # generic fallback for every crop.
        growth_planner_path = os.path.join('knowledge_base', 'growth_planner.json')
        if crop_name and os.path.exists(growth_planner_path):
            try:
                with open(growth_planner_path, 'r', encoding='utf-8') as f:
                    all_plans = json.load(f)
                kb_key = next((k for k in all_plans if k.lower() == str(crop_name).lower()), None)
                crop_entry = all_plans.get(kb_key) if kb_key else None
                if crop_entry and 'stages' in crop_entry:
                    knowledge_crop = kb_key
                    growth_plan = []
                    for s in crop_entry['stages']:
                        day_val = s.get('day', 1)
                        week_str = f"Week {int((day_val - 1) / 7) + 1}" if day_val > 1 else "Week 1"
                        growth_plan.append({
                            'week': week_str,
                            'stage': s.get('title', 'Operations'),
                            'action': s.get('description', '')
                        })
            except Exception as e:
                print(f"Error reading growth_planner.json: {e}")

        growth_plan_source = 'knowledge_base/growth_planner.json' if growth_plan else None
        if not growth_plan:
            # No knowledge-base entry for this crop. Return an explicitly
            # labelled generic starter instead of inventing a crop-specific
            # schedule we do not have data for.
            growth_plan = [
                {"week": "Weeks 1-4", "stage": "Sowing & Germination",
                 "action": "Sow seeds at recommended depth, keep soil moist and weed-free. "
                           "No crop-specific schedule is available for this crop."}
            ]
            growth_plan_source = 'generic-fallback'

        # Crop specific disease advisory (same case-insensitive lookup)
        disease_advisory = []
        disease_db_path = os.path.join('knowledge_base', 'crop_disease.json')
        if crop_name and os.path.exists(disease_db_path):
            try:
                with open(disease_db_path, 'r', encoding='utf-8') as f:
                    all_diseases = json.load(f)
                kb_key = next((k for k in all_diseases if k.lower() == str(knowledge_crop).lower()), None)
                crop_disease_entry = all_diseases.get(kb_key) if kb_key else None
                if crop_disease_entry and 'diseases' in crop_disease_entry:
                    disease_advisory = crop_disease_entry['diseases']
            except Exception as e:
                print(f"Error reading crop_disease.json: {e}")

        log_prediction(user_id, 'crop', {
            'nitrogen': n, 'phosphorus': p, 'potassium': k,
            'temperature': temp, 'humidity': hum, 'ph': ph, 'rainfall': rain
        }, result)

        return jsonify({
            'result': result,
            'soil_analysis': soil_analysis,
            'growth_plan': growth_plan,
            'growth_plan_source': growth_plan_source,
            'disease_advisory': disease_advisory
        })
    return jsonify({"error": "Method not allowed"}), 405

@app.route('/api/yield-prediction', methods=['GET', 'POST'])
def yield_prediction():
    user_id = session.get('user_id') if not session.get('is_guest') else None
        
    result = None
    market_analysis = None
    
    global vqc_yield_model

    crops = yield_crop_options()
    
    if request.method == 'POST':
        req_data = _json_body_or_form()
        if req_data is None:
            return _json_error("Request body must be valid JSON.")
        crop = req_data.get('crop')
        # `season` is DEPRECATED: accepted for old clients, never a model input.
        season = req_data.get('season')
        # Payload: {crop, area_hectares} — `area` is the legacy alias and is
        # still accepted so older clients keep working. The field is validated
        # here (present-but-null/non-numeric/non-positive -> JSON 400) instead of
        # letting float() raise a 500; an entirely omitted field still defaults
        # to 1 hectare for backwards compatibility.
        try:
            area = _coerce_number(
                req_data.get('area_hectares', req_data.get('area', 1)),
                'area_hectares', positive=True)
        except ValueError as exc:
            return _json_error(str(exc))
        classical, quantum, notes = run_yield_models(crop, area, season)
        if classical is None:
            return jsonify({"status": "error", "message": notes}), 503

        # Both models predict the harvest of the requested area; this API reports
        # tonnes per hectare, which is what the app labels and multiplies back out.
        #
        # `classical` IS the user-facing figure. The quantum leg is accurate on
        # district TOTALS (grouped test R2 0.911) but its per-hectare output is
        # unreliable — measured per-ha test R2 -102, and at areas <500 ha its
        # per-ha MAE is 19.2 t/ha vs the RF's 0.27 — because it predicts totals
        # with a positive intercept, so dividing by a small area explodes. It is
        # therefore reported for transparency and EXCLUDED from the user-facing
        # number (previously it was averaged in, which inflated revenue figures).
        ensemble = classical

        result = {
            'classical': classical,
            'quantum': quantum,
            'ensemble': ensemble,
            'quantum_available': quantum is not None,
            'quantum_experimental': quantum is not None,
            'units': 'tonnes per hectare',
        }

        # ---- Unit and area semantics, stated rather than implied -------------
        # The served figure is tonnes per hectare ONLY. "Total tonnes" is not a
        # model output: it is the arithmetic product of that figure and the
        # requested area, and the per-hectare figure itself comes from a model
        # fitted on DISTRICT-level annual statistics whose Area_Hectares feature
        # is a district aggregate. Multiplying a district average by a farmer's
        # field area is therefore an extrapolation, and it is labelled as one so
        # a product can never be read as a field measurement. Every number below
        # is either reported by the model or is plain arithmetic on it.
        try:
            scaled = scale_per_hectare_to_total(
                float(ensemble), area,
                area_kind=AREA_KIND_FIELD,
                estimate_basis=BASIS_DISTRICT_AGGREGATE)
            result['yield_per_hectare'] = scaled['yield_per_hectare']
            result['total_tonnes'] = scaled['total_tonnes']
            result['total_units'] = UNIT_TOTAL
            result['area_hectares'] = scaled['area_hectares']
            result['estimate_basis'] = BASIS_DISTRICT_AGGREGATE
            result['basis_description'] = BASIS_DESCRIPTIONS[BASIS_DISTRICT_AGGREGATE]
            result['is_extrapolation'] = scaled['is_extrapolation']
            result['caveats'] = list(scaled['caveats'])
        except AreaSemanticsError as exc:
            return _json_error(str(exc))
        if quantum is not None:
            result['quantum_note'] = (
                'Experimental: the quantum leg is trained on district totals and its '
                'per-hectare accuracy is unreliable at small areas, so it is excluded '
                'from the reported yield. Use `classical`/`ensemble` as the '
                'user-facing figure.')
        if notes:
            result['error'] = notes
            
        # Determine Market Price and Profitability from market_analysis.json.
        # Every number below is either read from the knowledge base or is plain
        # arithmetic on the model's own predicted yield. The previous version
        # invented prices (a hard-coded price table) and a cost-per-hectare for
        # any crop with no knowledge-base entry, so "profit" was fabricated
        # finance. Crops without KB data now return an explicit unavailability
        # object instead.
        market_info = None
        market_source = None
        market_db_path = os.path.join('knowledge_base', 'market_analysis.json')
        if os.path.exists(market_db_path):
            try:
                with open(market_db_path, 'r', encoding='utf-8') as f:
                    all_market = json.load(f)
                kb_key = next((k for k in all_market if k.lower() == str(crop).lower()), None)
                if kb_key:
                    market_info = all_market[kb_key]
                    market_source = f'knowledge_base/market_analysis.json#{kb_key}'
            except Exception as e:
                print(f"Error reading market_analysis.json: {e}")

        if market_info and market_info.get('price_per_tonne'):
            price = float(market_info['price_per_tonne'])
            cost = market_info.get('cost_per_hectare')
            # The reported yield is per hectare, so revenue covers the planted area.
            gross_revenue = float(result['ensemble']) * area * price
            net_profit = (gross_revenue - area * float(cost)) if cost is not None else None
            market_analysis = {
                'price_per_tonne': f"₹{round(price):,}",
                'gross_revenue': f"₹{round(gross_revenue):,}",
                'total_cost': f"₹{round(area * float(cost)):,}" if cost is not None else None,
                'net_profit': f"₹{round(net_profit):,}" if net_profit is not None else None,
                'profit_sign': (1 if net_profit >= 0 else 0) if net_profit is not None else None,
                'demand': market_info.get('demand'),
                'trend': market_info.get('trend'),
                'data_source': market_source,
                'note': (None if cost is not None else
                         'The knowledge base has no cost-of-cultivation figure for this '
                         'crop, so net profit is not estimated.'),
            }
        else:
            market_analysis = {
                'data_source': None,
                'note': f'No market analysis entry for {crop!r} in knowledge_base/market_analysis.json; '
                        f'price and profit are unavailable for this crop.',
            }
        
        log_prediction(user_id, 'yield', {
            'crop': crop, 'area_hectares': area,
            **({'season': season, 'season_ignored': True} if season else {}),
        }, result)
            
        return jsonify({
            'result': result,
            'market_analysis': market_analysis,
            'crops': crops,
            'contract': yield_contract_info(),
        })
    return jsonify({"error": "Method not allowed"}), 405


@app.route('/api/yield-prediction/experimental', methods=['GET', 'POST'])
def yield_prediction_experimental():
    """EXPERIMENTAL district-level yield contract: Crop + District -> t/ha.

    Separate from the served endpoint on purpose. The served contract is
    ``Crop + Area_Hectares`` and is pinned by tests/test_yield_contract_guard.py;
    this one adds the only other input the source data actually contains
    (district), removes the area from the model features, and refuses every
    input it cannot support instead of inventing a default.

    The estimate is district-level. It is never labelled field-level, and the
    total for a field is reported as the explicit extrapolation it is.
    """
    if not experimental_yield_contract.available:
        return jsonify({
            'status': 'error',
            'message': 'Experimental district-level yield model is unavailable.',
            'detail': experimental_yield_contract.load_error,
        }), 503

    contract_block = experimental_yield_contract.contract_info()

    if request.method != 'POST':
        return jsonify({
            'status': 'ok',
            'contract': contract_block,
            'crops': experimental_yield_contract.crop_options(),
            'districts': experimental_yield_contract.district_options(),
        })

    req_data = _json_body_or_form()
    if req_data is None:
        return _json_error('Request body must be valid JSON.')

    supported = {'crop', 'district', 'area_hectares'}
    extra = {key: value for key, value in req_data.items() if key not in supported}

    try:
        prediction = experimental_yield_contract.predict(
            req_data.get('crop'), req_data.get('district'),
            req_data.get('area_hectares'), **extra)
    except UnsupportedInputError as exc:
        return jsonify({
            'status': 'error',
            'error': 'unsupported_input',
            'message': str(exc),
            'contract': contract_block,
        }), 400
    except AreaSemanticsError as exc:
        return jsonify({
            'status': 'error',
            'error': 'invalid_area',
            'message': str(exc),
            'contract': contract_block,
        }), 400
    except ExperimentalModelUnavailable as exc:
        return jsonify({
            'status': 'error',
            'message': str(exc),
            'contract': contract_block,
        }), 503

    user_id = session.get('user_id') if not session.get('is_guest') else None
    log_prediction(user_id, 'yield_experimental', {
        'crop': prediction['crop'],
        'district': prediction['district'],
        'area_hectares': prediction['area_hectares'],
    }, prediction)

    return jsonify({
        'result': prediction,
        'contract': contract_block,
        'crops': experimental_yield_contract.crop_options(),
        'districts': experimental_yield_contract.district_options(),
    })


@app.route('/api/seed-viability', methods=['GET', 'POST'])
def seed_viability():
    user_id = session.get('user_id') if not session.get('is_guest') else None
        
    result = None
    if request.method == 'POST':
        req_data = _json_body_or_form()
        if req_data is None:
            return _json_error("Request body must be valid JSON.")
        try:
            moisture = _coerce_number(req_data.get('moisture'), 'moisture', default=0)
            weight = _coerce_number(req_data.get('weight'), 'weight', default=0)
        except ValueError as exc:
            return _json_error(str(exc))

        classical, quantum, notes, probability = run_seed_models(moisture, weight)
        if classical is None:
            return jsonify({"status": "error", "message": notes}), 503

        # The ensemble keeps the classical verdict as the deciding vote. When the
        # VQC could not be evaluated the quantum field says so instead of echoing
        # the classical answer as if a second model had produced it.
        result = {
            'classical': classical,
            'quantum': quantum if quantum is not None else 'Unavailable',
            'ensemble': classical,
            'agreement': quantum is None or quantum == classical,
            'viability_score': round(probability * 100, 1) if probability is not None else None,
            'quality_class': seed_quality_class(probability),
            'quality_source': 'derived from the classical model probability; not an official certification',
        }
        if notes:
            result['error'] = notes

        log_prediction(user_id, 'seed', {
            'moisture': moisture, 'weight': weight
        }, result)

        return jsonify({'result': result})
    return jsonify({"error": "Method not allowed"}), 405

@app.route('/api/storage-recommendation', methods=['GET', 'POST'])
def storage_recommendation():
    user_id = session.get('user_id') if not session.get('is_guest') else None
        
    result = None
    crop = None
    storage_db_path = os.path.join('knowledge_base', 'storage_db.json')
    db = {}
    if os.path.exists(storage_db_path):
        try:
            with open(storage_db_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception as e:
            print(f"Error reading storage database: {e}")
            
    crops = sorted(list(db.keys())) if db else ["Rice", "Wheat", "Maize", "Sugarcane", "Cotton"]

    def _case_insensitive_lookup(table, key):
        """Return (value, matched_key). The storage KB uses Title-case crop keys."""
        if not table or key is None:
            return None, None
        if key in table:
            return table[key], key
        lowered = str(key).strip().lower()
        for existing, value in table.items():
            if str(existing).strip().lower() == lowered:
                return value, existing
        return None, None

    # Static, crop-specific storage protocol from the knowledge base -- NOT live
    # sensor or weather telemetry. The values therefore repeat for a given crop
    # by design; the response labels that origin explicitly so the app never
    # presents these fixed guidelines as live readings.
    GENERIC_STORAGE_DEFAULT = {
        "temp": "15-25°C",
        "hum": "50-70%",
        "pres": "Standard dry storage ventilated area.",
        "shelf_life": "3-6 months",
        "fungus": "Monitor closely for mold.",
        "insects": "Use standard grain protective bags.",
        "risk_score": 30,
    }

    if request.method == 'POST':
        req_data = request.get_json(silent=True) if request.is_json else request.form
        crop = (req_data or {}).get('crop')
        row, matched_key = _case_insensitive_lookup(db, crop)
        kb_hit = row is not None
        result = dict(row) if kb_hit else dict(GENERIC_STORAGE_DEFAULT)
        result['source'] = f"knowledge_base/storage_db.json#{matched_key}" if kb_hit else None
        # A KB miss must never be labelled as a crop-specific protocol: generic
        # defaults are reported as generic so the app cannot present them as
        # this crop's own storage specification.
        result['data_type'] = 'static_knowledge_base' if kb_hit else 'generic_default'
        result['crop_specific'] = bool(kb_hit)
        result['live_telemetry'] = False
        result['protocol_note'] = (
            f"Guideline values from SeedIQ storage knowledge base (entry: {matched_key}); "
            "not live sensor telemetry."
            if kb_hit else
            "No crop-specific storage protocol was found. Generic guideline values are "
            "shown; they are not specific to this crop and are not live sensor or "
            "weather readings."
        )
        result['note'] = result['protocol_note']
        log_prediction(user_id, 'storage', {'crop': crop}, result)

        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({'result': result, 'crop': crop, 'crops': crops})
        
    try:
        return render_template('storage_recommendation.html', result=result, crop=crop, crops=crops)
    except Exception:
        return jsonify({'result': result, 'crop': crop, 'crops': crops})


@app.route('/api/quantum-ml', methods=['GET', 'POST'])
def quantum_ml():
    user_id = session.get('user_id') if not session.get('is_guest') else None
        
    result = None
    inputs = {}
    
    global rf_model, crop_scaler, crop_encoder, vqc_crop_model
    global meta_model
    
    if request.method == 'POST':
        # The crop stack is the one leg whose artifacts match the vector built
        # below. The yield and seed legs load their contract-matched models
        # through run_yield_models() / run_seed_models().
        if not rf_model: rf_model = load_helper('rf_model.pkl')
        if not crop_scaler: crop_scaler = load_helper('crop_scaler.pkl')
        crop_enc = get_crop_encoder()
        if not vqc_crop_model: vqc_crop_model = load_helper('vqc_crop_model.pkl')
        if not meta_model: meta_model = load_helper('meta_model.pkl')
        
        # 1. Get Crop inputs
        req_data = _json_body_or_form()
        if req_data is None:
            return _json_error("Request body must be valid JSON.")
        try:
            n = _coerce_number(req_data.get('nitrogen'), 'nitrogen', default=0)
            p = _coerce_number(req_data.get('phosphorus'), 'phosphorus', default=0)
            k = _coerce_number(req_data.get('potassium'), 'potassium', default=0)
            temp = _coerce_number(req_data.get('temperature'), 'temperature', default=0)
            hum = _coerce_number(req_data.get('humidity'), 'humidity', default=0)
            ph = _coerce_number(req_data.get('ph'), 'ph', default=0)
            rain = _coerce_number(req_data.get('rainfall'), 'rainfall', default=0)

            # 2. Get Yield inputs
            crop = req_data.get('crop')
            # Accepted for backwards compatibility only; the yield leg ignores it.
            season = req_data.get('season')
            # Payload: {crop, area_hectares} — `area` is the legacy alias, still
            # accepted so older clients keep working.
            area = _coerce_number(req_data.get('area_hectares', req_data.get('area', 1)),
                                  'area_hectares', positive=True)

            # 3. Get Seed inputs
            moisture = _coerce_number(req_data.get('moisture'), 'moisture', default=0)
            weight = _coerce_number(req_data.get('weight'), 'weight', default=0)
        except ValueError as exc:
            return _json_error(str(exc))
        
        inputs = {k_: v for k_, v in req_data.items() if isinstance(v, (str, int, float))}
        leg_notes = []
        
        try:
            # Step A: Crop base predictions
            if rf_model and crop_scaler and crop_enc:
                c_df = pd.DataFrame([[n, p, k, temp, hum, ph, rain]], 
                                    columns=['Nitrogen', 'Phosphorus', 'Potassium', 'Temperature', 'Humidity', 'pH', 'Rainfall'])
                c_feats = crop_scaler.transform(c_df)
                pred_rf_int = rf_model.predict(c_feats)[0]
                num_classes = len(crop_enc.classes_) if hasattr(crop_enc, 'classes_') and crop_enc.classes_ is not None and len(crop_enc.classes_) > 1 else len(STANDARD_CROP_CLASSES)
                pred_rf_val = pred_rf_int / (num_classes - 1 + 1e-9)
                pred_rf_name = decode_crop_name(crop_enc, pred_rf_int)
                
                if vqc_crop_model:
                    pred_qml_int = vqc_crop_model.predict(c_feats)[0]
                    pred_qml_val = pred_qml_int / (num_classes - 1 + 1e-9)
                    pred_qml_name = decode_crop_name(crop_enc, pred_qml_int)
                else:
                    pred_qml_val = pred_rf_val
                    pred_qml_name = pred_rf_name
                    leg_notes.append("Crop VQC unavailable; the crop quantum column mirrors the classical model.")
            else:
                raise RuntimeError("Crop models are not available on the server.")
                
            # Step B: Yield predictions — the same contract-matched models behind
            # /api/yield-prediction, reported in tonnes per hectare.
            pred_xgb, pred_qml_yield, yield_notes = run_yield_models(crop, area, season)
            if pred_xgb is None:
                raise RuntimeError(yield_notes)
            if yield_notes:
                leg_notes.append(yield_notes)
            if pred_qml_yield is None:
                pred_qml_yield = pred_xgb
                leg_notes.append("Yield VQR unavailable; the yield quantum column mirrors the classical model.")
            pred_xgb_val = float(np.clip(pred_xgb / 50.0, 0.0, 1.0))
            pred_qml_yield_val = float(np.clip(pred_qml_yield / 50.0, 0.0, 1.0))
                
            # Step C: Seed predictions — the same contract-matched models behind
            # /api/seed-viability (raw moisture % plus 100-seed weight).
            seed_classical, seed_quantum, seed_notes, _seed_probability = run_seed_models(moisture, weight)
            if seed_classical is None:
                raise RuntimeError(seed_notes)
            if seed_notes:
                leg_notes.append(seed_notes)
            if seed_quantum is None:
                seed_quantum = seed_classical
                leg_notes.append("Seed VQC unavailable; the seed quantum column mirrors the classical model.")
            # Shared encoding: identical to the training-side meta feature by
            # construction (see seed_viability_semantics).
            pred_svm_val = viable_flag_from_label(seed_classical)
            pred_qml_seed_val = viable_flag_from_label(seed_quantum)
                
            # Step D: Stacking Meta model prediction
            if meta_model:
                meta_features = np.array([[
                    pred_rf_val, pred_qml_val,
                    pred_xgb_val, pred_qml_yield_val,
                    pred_svm_val, pred_qml_seed_val
                ]])
                prob_success = meta_model.predict_proba(meta_features)[0, 1] * 100
                decision = "Optimal Performance (Success > 50%)" if prob_success >= 50 else "Suboptimal Performance (Success < 50%)"
            else:
                raise RuntimeError("Stacking meta model is not available on the server.")
                
            result = {
                'crop_rf': pred_rf_name,
                'crop_vqc': pred_qml_name,
                'yield_xgb': round(float(pred_xgb), 2),
                'yield_vqr': round(float(pred_qml_yield), 2),
                'seed_svm': seed_classical,
                'seed_vqc': seed_quantum,
                'prob_success': round(prob_success, 1),
                'decision': decision
            }
            if leg_notes:
                result['notes'] = leg_notes
        except Exception as e:
            print(f"Meta Model runtime calculation error: {e}")
            result = {
                'error': f"Computation error: {e}"
            }
        
        if result and 'error' not in result:
            log_prediction(user_id, 'quantum', {
                'nitrogen': n, 'phosphorus': p, 'potassium': k, 'ph': ph,
                'crop': crop, 'season': season, 'area': area
            }, result)
            
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({'result': result, 'inputs': inputs})
            
    try:
        return render_template('quantum_ml.html', result=result, inputs=inputs)
    except Exception:
        return jsonify({'result': result, 'inputs': inputs})


@app.route('/admin')
def admin_console():
    if 'user_id' not in session or not session.get('role') or session.get('role').lower() != 'admin':
        if request.is_json or request.headers.get('Accept') == 'application/json':
            return jsonify({"status": "error", "message": "Access Denied: Administrative console restricted to system administrators."}), 403
        flash("Access Denied: Administrative console restricted to system administrators.", "error")
        return redirect(url_for('dashboard'))
        
    stats = {
        'total_users': 0,
        'total_predictions': 0,
        'server_status': 'Operational',
        # Derived from the training registry instead of a hard-coded string:
        # the previous values claimed "Simulator Active (30 Epochs)" and 5
        # trained models regardless of what was actually on disk.
        'quantum_status': 'Simulated stand-in (no quantum hardware)',
        'models_trained': 0,
        'registry_entries': 0,
        'last_run_id': None,
        'last_run_at': None,
    }
    try:
        if os.path.exists(REGISTRY_FILE):
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                registry = json.load(f)
            if isinstance(registry, list):
                stats['registry_entries'] = len(registry)
                stats['models_trained'] = len({e.get('model_name') for e in registry if e.get('model_name')})
                if registry:
                    stats['last_run_id'] = registry[-1].get('run_id')
                    stats['last_run_at'] = registry[-1].get('timestamp')
                    stats['quantum_status'] = (
                        'Simulated stand-in (no quantum hardware)'
                        if any(e.get('simulated_quantum') for e in registry)
                        else 'Quantum models trained'
                    )
    except Exception as e:
        print(f"Error reading training registry for admin stats: {e}")

    # Load recent activity log
    activity_logs = []
    users_list = []
    try:
        with get_db() as conn:
            stats['total_users'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            stats['total_predictions'] = conn.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
            
            # Fetch users list
            users_rows = conn.execute('SELECT username, role FROM users LIMIT 10').fetchall()
            users_list = [{'username': u['username'], 'role': u['role']} for u in users_rows]
            
            # Fetch recent prediction entries
            pred_rows = conn.execute('SELECT prediction_type, timestamp FROM predictions ORDER BY timestamp DESC LIMIT 5').fetchall()
            activity_logs = [{'type': p['prediction_type'], 'time': p['timestamp']} for p in pred_rows]
    except Exception as e:
        print(f"Error loading admin statistics: {e}")
        users_list = []
        
    if request.is_json or request.headers.get('Accept') == 'application/json':
        return jsonify({"stats": stats, "users": users_list, "logs": activity_logs}), 200
    try:
        return render_template('admin.html', stats=stats, users=users_list, logs=activity_logs)
    except Exception:
        return jsonify({"stats": stats, "users": users_list, "logs": activity_logs}), 200

# ==============================================================================
# 5-MINUTE REAL-TIME DISTRICT SEED & CROP STORAGE INTELLIGENCE
# ==============================================================================
KARNATAKA_31_DISTRICTS_STORAGE = {
    "Bagalkot": {"name": "Bagalkot", "kannada": "ಬಾಗಲಕೋಟೆ", "region": "Northern Dry Zone", "crop": "Sugarcane", "capacity": 6200, "stock": 4850, "viability": 74, "pred_viability": 71, "moisture": "Moderate", "facility": "Aerated Bag Warehouse & Sugar Silo", "risk": "MONITOR"},
    "Ballari": {"name": "Ballari", "kannada": "ಬಳ್ಳಾರಿ", "region": "North Eastern Dry Zone", "crop": "Cotton", "capacity": 8500, "stock": 6100, "viability": 78, "pred_viability": 74, "moisture": "Low", "facility": "Dry Bale Warehouse", "risk": "STABLE"},
    "Belagavi": {"name": "Belagavi", "kannada": "ಬೆಳಗಾವಿ", "region": "Northern Transition Zone", "crop": "Sugarcane", "capacity": 12500, "stock": 9800, "viability": 84, "pred_viability": 81, "moisture": "Moderate", "facility": "Controlled Atmosphere Complex", "risk": "STABLE"},
    "Bengaluru Rural": {"name": "Bengaluru Rural", "kannada": "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ", "region": "Eastern Dry Zone", "crop": "Ragi", "capacity": 4500, "stock": 3100, "viability": 80, "pred_viability": 78, "moisture": "Low", "facility": "Dry Grain Silos", "risk": "STABLE"},
    "Bengaluru Urban": {"name": "Bengaluru Urban", "kannada": "ಬೆಂಗಳೂರು ನಗರ", "region": "Eastern Dry Zone", "crop": "Maize", "capacity": 5000, "stock": 2900, "viability": 76, "pred_viability": 73, "moisture": "Moderate", "facility": "Metro Cold Hub & Distribution", "risk": "MONITOR"},
    "Bidar": {"name": "Bidar", "kannada": "ಬೀದರ್", "region": "North Eastern Transition Zone", "crop": "Pulses", "capacity": 5500, "stock": 3400, "viability": 71, "pred_viability": 66, "moisture": "Moderate", "facility": "Hermetic Pulse Storage Unit", "risk": "MONITOR"},
    "Chamarajanagar": {"name": "Chamarajanagar", "kannada": "ಚಾಮರಾಜನಗರ", "region": "Southern Dry Zone", "crop": "Turmeric", "capacity": 4200, "stock": 2600, "viability": 79, "pred_viability": 76, "moisture": "Low", "facility": "Cured Spice Warehousing", "risk": "STABLE"},
    "Chikkaballapur": {"name": "Chikkaballapur", "kannada": "ಚಿಕ್ಕಬಳ್ಳಾಪುರ", "region": "Eastern Dry Zone", "crop": "Groundnut", "capacity": 4800, "stock": 2100, "viability": 58, "pred_viability": 52, "moisture": "High", "facility": "Pod Drying & Dry Storage", "risk": "WARNING"},
    "Chikkamagaluru": {"name": "Chikkamagaluru", "kannada": "ಚಿಕ್ಕಮಗಳೂರು", "region": "Central Dry / Hill Zone", "crop": "Coffee", "capacity": 9200, "stock": 7400, "viability": 86, "pred_viability": 83, "moisture": "Moderate", "facility": "Hermetic Coffee Parchment Storage", "risk": "STABLE"},
    "Chitradurga": {"name": "Chitradurga", "kannada": "ಚಿತ್ರದುರ್ಗ", "region": "Central Dry Zone", "crop": "Groundnut", "capacity": 5400, "stock": 3600, "viability": 72, "pred_viability": 68, "moisture": "Low", "facility": "Ventilated Grain Depot", "risk": "MONITOR"},
    "Dakshina Kannada": {"name": "Dakshina Kannada", "kannada": "ದಕ್ಷಿಣ ಕನ್ನಡ", "region": "Coastal Zone", "crop": "Rice", "capacity": 7100, "stock": 3800, "viability": 54, "pred_viability": 48, "moisture": "High", "facility": "Dehumidified Coastal Silo", "risk": "CRITICAL"},
    "Davanagere": {"name": "Davanagere", "kannada": "ದಾವಣಗೆರೆ", "region": "Central Dry Zone", "crop": "Maize", "capacity": 8800, "stock": 6900, "viability": 82, "pred_viability": 80, "moisture": "Low", "facility": "Aerated Metal Grain Bins", "risk": "STABLE"},
    "Dharwad": {"name": "Dharwad", "kannada": "ಧಾರವಾಡ", "region": "Northern Transition Zone", "crop": "Soybean", "capacity": 6500, "stock": 4200, "viability": 77, "pred_viability": 74, "moisture": "Moderate", "facility": "Seed Certification Silo Complex", "risk": "STABLE"},
    "Gadag": {"name": "Gadag", "kannada": "ಗದಗ", "region": "Northern Dry Zone", "crop": "Onion", "capacity": 5200, "stock": 3100, "viability": 63, "pred_viability": 58, "moisture": "Moderate", "facility": "Naturally Ventilated Onion Structures", "risk": "WARNING"},
    "Hassan": {"name": "Hassan", "kannada": "ಹಾಸನ", "region": "Southern Transition Zone", "crop": "Potato", "capacity": 7800, "stock": 5400, "viability": 81, "pred_viability": 78, "moisture": "Moderate", "facility": "Cold Storage & Sprout Inhibition Facility", "risk": "STABLE"},
    "Haveri": {"name": "Haveri", "kannada": "ಹಾವೇರಿ", "region": "Northern Transition Zone", "crop": "Maize", "capacity": 7300, "stock": 5200, "viability": 80, "pred_viability": 77, "moisture": "Low", "facility": "Grain Depot Complex", "risk": "STABLE"},
    "Kalaburagi": {"name": "Kalaburagi", "kannada": "ಕಲಬುರಗಿ", "region": "North Eastern Dry Zone", "crop": "Pulses", "capacity": 8900, "stock": 6300, "viability": 79, "pred_viability": 76, "moisture": "Low", "facility": "Tur Dal Mega Silos", "risk": "STABLE"},
    "Kodagu": {"name": "Kodagu", "kannada": "ಕೊಡಗು", "region": "Hilly Zone", "crop": "Coffee", "capacity": 8400, "stock": 6700, "viability": 88, "pred_viability": 86, "moisture": "Moderate", "facility": "Altitude Hermetic Storage", "risk": "STABLE"},
    "Kolar": {"name": "Kolar", "kannada": "ಕೋಲಾರ", "region": "Eastern Dry Zone", "crop": "Tomato", "capacity": 4600, "stock": 1900, "viability": 44, "pred_viability": 38, "moisture": "High", "facility": "Cooling Packhouse & Cold Storage", "risk": "CRITICAL"},
    "Koppal": {"name": "Koppal", "kannada": "ಕೊಪ್ಪಳ", "region": "Northern Dry Zone", "crop": "Rice", "capacity": 6900, "stock": 4800, "viability": 76, "pred_viability": 73, "moisture": "Low", "facility": "Paddy Warehouse Complex", "risk": "MONITOR"},
    "Mandya": {"name": "Mandya", "kannada": "ಮಂಡ್ಯ", "region": "Southern Dry Zone", "crop": "Rice", "capacity": 9500, "stock": 7900, "viability": 85, "pred_viability": 82, "moisture": "Low", "facility": "Modern Aerated Silo Battery", "risk": "STABLE"},
    "Mysuru": {"name": "Mysuru", "kannada": "ಮೈಸೂರು", "region": "Southern Dry Zone", "crop": "Cotton", "capacity": 8200, "stock": 6100, "viability": 81, "pred_viability": 79, "moisture": "Low", "facility": "Regional Central Warehouse", "risk": "STABLE"},
    "Raichur": {"name": "Raichur", "kannada": "ರಾಯಚೂರು", "region": "North Eastern Dry Zone", "crop": "Rice", "capacity": 10500, "stock": 8800, "viability": 87, "pred_viability": 84, "moisture": "Low", "facility": "Paddy Silo Terminal", "risk": "STABLE"},
    "Ramanagara": {"name": "Ramanagara", "kannada": "ರಾಮನಗರ", "region": "Eastern Dry Zone", "crop": "Ragi", "capacity": 4300, "stock": 2900, "viability": 79, "pred_viability": 76, "moisture": "Low", "facility": "Grain Silos & Seed Center", "risk": "STABLE"},
    "Shivamogga": {"name": "Shivamogga", "kannada": "ಶಿವಮೊಗ್ಗ", "region": "Southern Transition Zone", "crop": "Rice", "capacity": 8600, "stock": 6400, "viability": 82, "pred_viability": 79, "moisture": "Moderate", "facility": "Central Godown & Grain Storage", "risk": "STABLE"},
    "Tumakuru": {"name": "Tumakuru", "kannada": "ತುಮಕೂರು", "region": "Central Dry Zone", "crop": "Coconut", "capacity": 6800, "stock": 4900, "viability": 83, "pred_viability": 80, "moisture": "Low", "facility": "Dry Ventilated Copra Store", "risk": "STABLE"},
    "Udupi": {"name": "Udupi", "kannada": "ಉಡುಪಿ", "region": "Coastal Zone", "crop": "Rice", "capacity": 5800, "stock": 2700, "viability": 48, "pred_viability": 42, "moisture": "High", "facility": "Coastal Dehumidified Storage", "risk": "CRITICAL"},
    "Uttara Kannada": {"name": "Uttara Kannada", "kannada": "ಉತ್ತರ ಕನ್ನಡ", "region": "Coastal Zone", "crop": "Rice", "capacity": 6200, "stock": 3500, "viability": 60, "pred_viability": 54, "moisture": "High", "facility": "Aerated Coastal Godown", "risk": "WARNING"},
    "Vijayanagara": {"name": "Vijayanagara", "kannada": "ವಿಜಯನಗರ", "region": "North Eastern Dry Zone", "crop": "Maize", "capacity": 6700, "stock": 4800, "viability": 80, "pred_viability": 77, "moisture": "Low", "facility": "Dry Grain Storage Bins", "risk": "STABLE"},
    "Vijayapura": {"name": "Vijayapura", "kannada": "ವಿಜಯಪುರ", "region": "Northern Dry Zone", "crop": "Millets", "capacity": 6100, "stock": 3900, "viability": 75, "pred_viability": 72, "moisture": "Low", "facility": "Cold Storage & Dry Silos", "risk": "MONITOR"},
    "Yadgir": {"name": "Yadgir", "kannada": "ಯಾದಗಿರಿ", "region": "North Eastern Dry Zone", "crop": "Pulses", "capacity": 5100, "stock": 3200, "viability": 72, "pred_viability": 69, "moisture": "Low", "facility": "Dal Storage Warehouse", "risk": "MONITOR"}
}

def _get_crop_storage_specs(crop_name):
    storage_db_path = os.path.join(os.path.dirname(__file__), 'knowledge_base', 'storage_db.json')
    if os.path.exists(storage_db_path):
        try:
            with open(storage_db_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
            if crop_name in db:
                return db[crop_name]
            # The KB keys are Title-case; accept either casing.
            lowered = str(crop_name).strip().lower()
            for existing, spec in db.items():
                if str(existing).strip().lower() == lowered:
                    return spec
        except Exception:
            pass
    # Fallback storage defaults
    return {
        "temp": "15-22°C",
        "hum": "55-65%",
        "pres": "Standard dry ventilated store.",
        "shelf_life": "6-12 months",
        "fungus": "Monitor moisture levels.",
        "insects": "Store in hermetic bags.",
        "risk_score": 25
    }

@app.route('/api/districts/storage-live', methods=['GET'])
def get_live_district_storage():
    """
    Static district storage REFERENCE dataset for Karnataka's 31 districts.

    Every capacity/stock/viability/moisture value comes from the hardcoded
    KARNATAKA_31_DISTRICTS_STORAGE table — there is no sensor, weather or
    logistics feed behind it. The response states that explicitly via
    data_type / live_telemetry / note; the sync fields describe the client's
    re-read cadence of this same static payload, not a telemetry refresh.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    seconds_into_interval = (now.minute % 5) * 60 + now.second
    next_sync_seconds = max(1, 300 - seconds_into_interval)

    # Calculate live aggregated metrics
    districts_list = []
    critical_alerts = 0
    warning_alerts = 0
    stable_count = 0
    total_stock = 0
    total_capacity = 0

    for d_id, d_data in KARNATAKA_31_DISTRICTS_STORAGE.items():
        crop_specs = _get_crop_storage_specs(d_data["crop"])
        occupancy_pct = round((d_data["stock"] / d_data["capacity"]) * 100, 1)
        total_stock += d_data["stock"]
        total_capacity += d_data["capacity"]

        risk_level = d_data["risk"]
        if risk_level == "CRITICAL":
            critical_alerts += 1
            alert_msg = f"Critical seed viability drop ({d_data['viability']}%). Emergency redistribution required."
        elif risk_level == "WARNING":
            warning_alerts += 1
            alert_msg = f"Elevated moisture risk in storage. Viability declining to {d_data['pred_viability']}%."
        elif risk_level == "MONITOR":
            alert_msg = f"Storage conditions stable with minor moisture monitoring required."
        else:
            stable_count += 1
            alert_msg = f"Optimal storage environment. Germination viability at {d_data['viability']}%."

        is_redistribution_source = (risk_level == "STABLE" and occupancy_pct < 85 and d_data["viability"] >= 80)

        districts_list.append({
            "district_id": d_id,
            "district_name": d_data["name"],
            "kannada_name": d_data["kannada"],
            "region": d_data["region"],
            "primary_crop": d_data["crop"],
            "seed_storage": {
                "available_stock_tons": d_data["stock"],
                "total_capacity_tons": d_data["capacity"],
                "occupancy_percentage": occupancy_pct,
                "current_viability_percentage": d_data["viability"],
                "predicted_viability_percentage": d_data["pred_viability"],
                "moisture_vulnerability": d_data["moisture"],
                "risk_level": risk_level,
                "alert_message": alert_msg,
                "redistribution_eligible": is_redistribution_source
            },
            "crop_storage": {
                "facility_type": d_data["facility"],
                "optimal_temp": crop_specs.get("temp", "15-22°C"),
                "optimal_humidity": crop_specs.get("hum", "60%"),
                "safe_shelf_life": crop_specs.get("shelf_life", "12 months"),
                "pest_and_fungus_risk": crop_specs.get("fungus", "Monitor closely for mold."),
                "preservation_protocol": crop_specs.get("pres", "Maintain dry aeration."),
                "risk_score": crop_specs.get("risk_score", 20)
            }
        })

    # Sort so critical and warning alerts appear first
    priority = {"CRITICAL": 0, "WARNING": 1, "MONITOR": 2, "STABLE": 3}
    districts_list.sort(key=lambda x: (priority.get(x["seed_storage"]["risk_level"], 4), x["district_name"]))

    return jsonify({
        "status": "success",
        "service": "SeedIQ District Storage Reference Dataset (static)",
        "data_type": "static_reference_dataset",
        "live_telemetry": False,
        "note": ("District capacity, stock, viability and moisture values are a static "
                 "reference dataset shipped with SeedIQ — not live sensor, weather or "
                 "logistics telemetry. 'last_updated' is when this response was built and "
                 "sync_interval_seconds is the client re-read cadence."),
        "last_updated": now.isoformat(),
        "sync_interval_seconds": 300,
        "next_sync_in_seconds": next_sync_seconds,
        "summary": {
            "total_districts": len(KARNATAKA_31_DISTRICTS_STORAGE),
            "critical_alerts": critical_alerts,
            "warning_alerts": warning_alerts,
            "stable_districts": stable_count,
            "total_stock_tons": total_stock,
            "total_capacity_tons": total_capacity,
            "statewide_occupancy_percentage": round((total_stock / max(1, total_capacity)) * 100, 1)
        },
        "districts": districts_list
    }), 200

@app.route('/api/notifications/district-storage', methods=['GET'])
def get_district_storage_notifications():
    """
    Karnataka district seed & crop storage notifications, derived from the static
    reference dataset (KARNATAKA_31_DISTRICTS_STORAGE) — NOT live telemetry.
    Delivers a unified list of up to max 21 high-priority district notifications.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    seconds_into_interval = (now.minute % 5) * 60 + now.second
    next_sync_seconds = max(1, 300 - seconds_into_interval)
    limit = min(int(request.args.get('limit', 21)), 21)

    all_notifications = []
    
    # Priority ranking for sorting: CRITICAL (0), WARNING (1), MONITOR (2), STABLE (3)
    risk_rank = {"CRITICAL": 0, "WARNING": 1, "MONITOR": 2, "STABLE": 3}

    for d_id, d_data in KARNATAKA_31_DISTRICTS_STORAGE.items():
        crop_specs = _get_crop_storage_specs(d_data["crop"])
        occupancy = round((d_data["stock"] / max(1, d_data["capacity"])) * 100, 1)
        risk = d_data["risk"]

        if risk == "CRITICAL":
            title = f"🚨 Critical Viability: {d_data['name']} ({d_data['kannada']})"
            message = f"Seed viability fallen to {d_data['viability']}%. High humidity risk in {d_data['facility']}. Urgent stock redistribution required."
            action = "Initiate Emergency Stock Redistribution"
        elif risk == "WARNING":
            title = f"⚠️ Moisture Risk Alert: {d_data['name']} ({d_data['kannada']})"
            message = f"Moisture vulnerability elevated in {d_data['facility']}. Projected viability dropping to {d_data['pred_viability']}%. Dehumidification needed."
            action = "Activate Aeration Blowers & Dehumidifiers"
        elif risk == "MONITOR":
            title = f"📊 Storage Capacity Surge: {d_data['name']} ({d_data['kannada']})"
            message = f"Warehouse occupancy at {occupancy}% ({d_data['stock']:,}T / {d_data['capacity']:,}T). {d_data['crop']} seeds requiring standard moisture inspection."
            action = "Audit Bin Temperature & Seed Moisture"
        else:
            title = f"✅ Optimal Seed Reserve: {d_data['name']} ({d_data['kannada']})"
            message = f"{d_data['stock']:,}T of certified {d_data['crop']} seeds in optimal health ({d_data['viability']}% viability). Eligible as regional redistribution source."
            action = "Available for Regional Redistribution"

        all_notifications.append({
            "id": f"notif_{d_id.lower().replace(' ', '_')}",
            "district_id": d_id,
            "district_name": d_data["name"],
            "kannada_name": d_data["kannada"],
            "region": d_data.get("region", "Karnataka"),
            "crop": d_data["crop"],
            "risk_level": risk,
            "current_viability": d_data["viability"],
            "predicted_viability": d_data["pred_viability"],
            "stock_tons": d_data["stock"],
            "capacity_tons": d_data["capacity"],
            "occupancy_pct": occupancy,
            "moisture_risk": d_data["moisture"],
            "facility": d_data["facility"],
            "safe_duration": crop_specs.get("shelf_life", "6-12 months"),
            "title": title,
            "message": message,
            "recommended_action": action,
            "timestamp": now.isoformat(),
            "time_ago": "Just now" if seconds_into_interval < 60 else f"{seconds_into_interval // 60}m ago",
            "redistribution_eligible": (risk == "STABLE" and occupancy < 85 and d_data["viability"] >= 80)
        })

    # Sort so most critical/vulnerable districts come first, then lowest viability, then highest occupancy
    all_notifications.sort(
        key=lambda n: (
            risk_rank.get(n["risk_level"], 4),
            n["current_viability"],
            -n["occupancy_pct"]
        )
    )

    # Limit to the 21 highest-priority district notifications
    top_21_notifications = all_notifications[:limit]

    critical_count = sum(1 for n in top_21_notifications if n["risk_level"] == "CRITICAL")
    warning_count = sum(1 for n in top_21_notifications if n["risk_level"] == "WARNING")
    monitor_count = sum(1 for n in top_21_notifications if n["risk_level"] == "MONITOR")
    stable_count = sum(1 for n in top_21_notifications if n["risk_level"] == "STABLE")

    return jsonify({
        "status": "success",
        "data_type": "static_reference_dataset",
        "live_telemetry": False,
        "note": ("These district notifications are computed from SeedIQ's static storage "
                 "reference dataset, not from live sensor or weather telemetry. "
                 "'last_synced' is when this response was built."),
        "last_synced": now.isoformat(),
        "next_sync_in_seconds": next_sync_seconds,
        "sync_frequency_minutes": 5,
        "max_limit": limit,
        "total_districts": len(KARNATAKA_31_DISTRICTS_STORAGE),
        "notifications_count": len(top_21_notifications),
        "active_alerts_count": len(top_21_notifications),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "monitor_count": monitor_count,
        "stable_count": stable_count,
        "notifications": top_21_notifications,
        "alerts": top_21_notifications
    }), 200

# ==============================================================================
# USER DATABASE & AUDIT LOGGING MAINTENANCE ENDPOINTS
# ==============================================================================
@app.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    """
    Returns all registered users with role and database provider.
    Accessible to Admin or Researcher roles.
    """
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Researcher']:
        return jsonify({"status": "error", "message": "Access Denied: Admin or Researcher privileges required."}), 403

    users = []
    try:
        with get_db() as conn:
            rows = conn.execute('''
                SELECT id, username, email, display_name, role, provider, created_at, updated_at, phone
                FROM users ORDER BY id ASC
            ''').fetchall()
            for r in rows:
                users.append({
                    "id": r['id'],
                    "username": r['username'],
                    "email": r['email'],
                    "phone": r['phone'],
                    "display_name": r['display_name'] or r['username'],
                    "role": r['role'] or 'Farmer',
                    "provider": r['provider'] or 'local',
                    "created_at": r['created_at']
                })
    except Exception as e:
        print(f"[ADMIN_USERS] SQLite query notice: {e}")

    # Also query Supabase profiles if available
    try:
        sb_success, sb_profiles = supabase.select_rows("profiles", "select=id,username,email,display_name,role,updated_at")
        if sb_success and sb_profiles:
            existing_emails = {u["email"].lower() for u in users if u.get("email")}
            for sp in sb_profiles:
                if sp.get("email") and sp["email"].lower() not in existing_emails:
                    users.append({
                        "id": sp.get("id"),
                        "username": sp.get("username", sp.get("email", "").split("@")[0]),
                        "email": sp.get("email"),
                        "display_name": sp.get("display_name"),
                        "role": sp.get("role", "Farmer"),
                        "provider": "supabase",
                        "created_at": sp.get("updated_at")
                    })
    except Exception as e:
        print(f"[ADMIN_USERS] Supabase profiles query notice: {e}")

    return jsonify({
        "status": "success",
        "total_users": len(users),
        "users": users
    }), 200

CONFIRM_PURGE_TOKEN = 'PURGE_ACTIVITY_LOGS'


@app.route('/api/admin/activity-logs/purge', methods=['POST'])
def admin_purge_activity_logs():
    """
    Permanently delete recorded activity-log rows (Admin only).

    This is the data-cleanup counterpart to /api/admin/activity-logs: it removes
    stored records so the console lists nothing old, while the logger and every
    future write path stay exactly as they were. Deleting rows is not the same as
    hiding the screen, and the unauthenticated caller cannot reach it.

    Body:
        {"confirm": "PURGE_ACTIVITY_LOGS",
         "before":  "YYYY-MM-DD HH:MM:SS",   # optional
         "user_ids": [...],                  # optional
         "event_types": [...]}               # optional
    """
    if 'user_id' not in session or session.get('role') != 'Admin':
        return jsonify({
            "status": "error",
            "message": "Access Denied: Administrator privileges required.",
        }), 403

    data = request.get_json(silent=True) or {}
    if str(data.get('confirm') or '').strip() != CONFIRM_PURGE_TOKEN:
        return jsonify({
            "status": "error",
            "message": f'Confirmation required: send {{"confirm":"{CONFIRM_PURGE_TOKEN}"}}.',
        }), 400

    before = (data.get('before') or '').strip() or None
    user_ids = data.get('user_ids') or None
    event_types = data.get('event_types') or None

    outcome = purge_activity_logs(before=before, user_ids=user_ids, event_types=event_types)
    total = (outcome.get('sqlite_deleted') or 0) + (outcome.get('supabase_deleted') or 0)

    return jsonify({
        "status": "success" if (outcome.get('sqlite_ok') or outcome.get('supabase_ok')) else "error",
        "message": (
            f"Removed {outcome.get('sqlite_deleted', 0)} local activity record(s)"
            + (f" and {outcome.get('supabase_deleted', 0)} mirrored record(s)." if outcome.get('supabase_ok') else ".")
        ),
        "deleted": outcome,
        "filters": {"before": before, "user_ids": user_ids, "event_types": event_types},
        "remaining": _activity_log_count(),
    }), 200


def _activity_log_count() -> int:
    """Row count in the local audit table, so a caller can confirm the purge."""
    try:
        with get_db() as conn:
            return int(conn.execute('SELECT COUNT(*) FROM activity_logs').fetchone()[0])
    except Exception:
        return -1


@app.route('/api/admin/activity-logs', methods=['GET'])
def admin_get_activity_logs():
    """
    Returns recent system audit and security logs.
    """
    if 'user_id' not in session or session.get('role') not in ['Admin', 'Researcher']:
        return jsonify({"status": "error", "message": "Access Denied: Admin or Researcher privileges required."}), 403

    limit = min(int(request.args.get('limit', 100)), 500)
    logs = []
    try:
        with get_db() as conn:
            rows = conn.execute('''
                SELECT id, user_id, event_type, details, status, ip_address, created_at
                FROM activity_logs ORDER BY id DESC LIMIT ?
            ''', (limit,)).fetchall()
            for r in rows:
                details_parsed = {}
                try:
                    details_parsed = json.loads(r['details']) if r['details'] else {}
                except Exception:
                    details_parsed = {"raw": r['details']}

                logs.append({
                    "id": r['id'],
                    "user_id": r['user_id'],
                    "event_type": r['event_type'],
                    "details": details_parsed,
                    "status": r['status'],
                    "ip_address": r['ip_address'],
                    "created_at": r['created_at']
                })
    except Exception as e:
        print(f"[ADMIN_LOGS] SQLite error: {e}")

    return jsonify({
        "status": "success",
        "count": len(logs),
        "total": _activity_log_count(),
        "logs": logs
    }), 200

# One-shot cleanup hook: set SEEDIQ_PURGE_ACTIVITY_LOGS_ON_START=1 on a deployment
# to clear the pre-existing development/test audit history during that boot. The
# flag is deliberately opt-in so a normal restart never discards audit records.
if os.environ.get("SEEDIQ_PURGE_ACTIVITY_LOGS_ON_START", "").strip().lower() in ("1", "true", "yes"):
    try:
        _startup_purge = purge_activity_logs()
        print(f"[ACTIVITY_LOGS] startup purge complete: {_startup_purge}")
    except Exception as _purge_err:
        print(f"[ACTIVITY_LOGS] startup purge failed: {_purge_err}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """Production health check probe for Render/Railway orchestration."""
    return jsonify({
        "status": "healthy",
        "service": "SeedIQ Backend Engine",
        "version": "4.3",
        "phone_auth": True,
        "sms_provider": phone_auth.active_sms_provider(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(host=host, port=port, debug=debug, use_reloader=False)
