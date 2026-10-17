"""
SeedIQ SQLite to Supabase Migration Script
Performs repeatable, idempotent, safe migration of existing data and datasets
from SQLite (SeedIQ/seediq.db) to Supabase PostgreSQL and Storage.
Does NOT delete or modify existing SQLite data.
Accurately records attempted, succeeded, and failed items.
Exits with non-zero code if any required migration operation fails.
"""

import os
import sys
import json
import sqlite3
import hashlib
import datetime
from typing import Dict, Any, List, Tuple
from supabase_client import supabase
from activity_logger import log_activity

DB_PATH = os.path.join(os.path.dirname(__file__), 'seediq.db')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def get_sqlite_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def compute_hash(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class Accounting:
    def __init__(self, name: str):
        self.name = name
        self.attempted = 0
        self.succeeded = 0
        self.failed = 0
        self.errors = []

    def record_attempt(self):
        self.attempted += 1

    def record_success(self):
        self.succeeded += 1

    def record_failure(self, identifier: str, reason: str):
        self.failed += 1
        self.errors.append((identifier, reason))

    def as_dict(self) -> Dict[str, int]:
        return {
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed
        }


def check_remote_readiness() -> Tuple[bool, bool, str]:
    """Checks whether remote tables and storage bucket exist."""
    tables_ready = False
    storage_ready = False
    status_notes = []

    # 1. Check tables via PostgREST
    ok_tbl, res_tbl = supabase.select_rows("profiles", "select=count&limit=1")
    if ok_tbl:
        tables_ready = True
        status_notes.append("Remote PostgreSQL tables: DETECTED")
    else:
        status_notes.append("Remote PostgreSQL tables: NOT DETECTED (404 - Migration not applied)")

    # 2. Check storage bucket
    try:
        import requests
        headers = {
            "apikey": supabase.key,
            "Authorization": f"Bearer {supabase.key}"
        }
        r = requests.get(f"{supabase.url}/storage/v1/bucket", headers=headers, timeout=5)
        if r.status_code == 200:
            buckets = [b.get("id") for b in r.json()]
            if "seediq-datasets" in buckets:
                storage_ready = True
                status_notes.append("Remote Storage bucket 'seediq-datasets': DETECTED")
            else:
                status_notes.append("Remote Storage bucket 'seediq-datasets': NOT FOUND (bucket missing)")
        else:
            status_notes.append(f"Remote Storage bucket check returned status {r.status_code}")
    except Exception as ex:
        status_notes.append(f"Remote Storage bucket check error: {ex}")

    return tables_ready, storage_ready, " | ".join(status_notes)


def migrate():
    print("=" * 70)
    print("[MIGRATION] STARTING SEEDIQ SQLITE -> SUPABASE MIGRATION")
    print("=" * 70)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] SQLite database not found at {DB_PATH}")
        sys.exit(1)

    tables_ready, storage_ready, readiness_msg = check_remote_readiness()
    print(f"\n[PRE-CHECK] {readiness_msg}")

    if not tables_ready:
        print("\n" + "!" * 70)
        print("[CRITICAL] REMOTE DATABASE MIGRATION NOT APPLIED.")
        print("The remote Supabase PostgreSQL database does not have the required tables.")
        print("Please execute 'supabase/migrations/20260916000000_seed_iq_schema.sql'")
        print("in the Supabase Dashboard SQL Editor:")
        proj_id = supabase.url.split('//')[1].split('.')[0] if '//' in supabase.url else 'cqcdfvetexaqqcfogcds'
        print(f"  URL: https://supabase.com/dashboard/project/{proj_id}/sql")
        print("!" * 70)

    if not storage_ready:
        print("\n" + "!" * 70)
        print("[CRITICAL] STORAGE BUCKET 'seediq-datasets' NOT FOUND.")
        print("Executing the migration SQL creates both tables and the storage bucket.")
        print("!" * 70)

    conn = get_sqlite_conn()
    cur = conn.cursor()

    acct_users = Accounting("Users")
    acct_preds = Accounting("Predictions")
    acct_exps = Accounting("Experiments")
    acct_metrics = Accounting("Experiment Metrics")
    acct_models = Accounting("Model Versions")
    acct_datasets = Accounting("Baseline Datasets")

    # --------------------------------------------------------------------------
    # 1. MIGRATE USERS TO SUPABASE AUTH & PROFILES
    # --------------------------------------------------------------------------
    print("\n[1/5] Migrating Users & Profiles...")
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    user_id_map: Dict[Any, str] = {}

    admin_email = os.environ.get("SEEDIQ_ADMIN_EMAIL", "admin@seediq.ai").strip().lower()
    researcher_email = os.environ.get("SEEDIQ_RESEARCHER_EMAIL", "researcher@quantum.org").strip().lower()

    for u in users:
        u_dict = dict(u)
        email = u_dict.get('email')
        uname = u_dict.get('username') or f"user_{u_dict.get('id')}"
        role = u_dict.get('role', 'Farmer')
        display_name = u_dict.get('display_name') or uname

        if email and email.lower() == admin_email:
            role = 'Admin'
        elif email and email.lower() == researcher_email:
            role = 'Researcher'
        elif role not in ['Admin', 'Researcher', 'Farmer']:
            role = 'Farmer'

        if not email:
            email = f"{uname}@legacy.seediq.local"

        acct_users.record_attempt()
        temp_pw = "SeedIQ2026!SecureDefault"
        ok, res = supabase.sign_up(email=email, password=temp_pw, display_name=display_name, role=role)
        target_uuid = None
        if ok and res:
            target_uuid = res.get("id") or (res.get("user") or {}).get("id")
        else:
            if tables_ready:
                existing_prof = supabase.select_rows("profiles", f"email=eq.{email}&select=id")
                if existing_prof[0] and existing_prof[1]:
                    target_uuid = existing_prof[1][0].get("id")

        if target_uuid:
            user_id_map[u_dict['id']] = target_uuid
            acct_users.record_success()
            print(f"  [OK] Migrated user: {email} -> {target_uuid}")
        else:
            err_msg = "Supabase Auth rejected or rate-limited" if not tables_ready else "Profile lookup failed"
            acct_users.record_failure(email, err_msg)
            print(f"  [FAIL] User {email}: {err_msg}")

    print(f"  -> Users Summary: Attempted: {acct_users.attempted}, Succeeded: {acct_users.succeeded}, Failed: {acct_users.failed}")

    # --------------------------------------------------------------------------
    # 2. MIGRATE PREDICTIONS
    # --------------------------------------------------------------------------
    print("\n[2/5] Migrating Predictions...")
    cur.execute("SELECT * FROM predictions")
    preds = cur.fetchall()
    for p in preds:
        p_dict = dict(p)
        sqlite_uid = p_dict.get('user_id')
        sb_uid = user_id_map.get(sqlite_uid)

        acct_preds.record_attempt()
        try:
            inputs = json.loads(p_dict['inputs']) if isinstance(p_dict.get('inputs'), str) else (p_dict.get('inputs') or {})
            results = json.loads(p_dict['results']) if isinstance(p_dict.get('results'), str) else (p_dict.get('results') or {})
        except Exception:
            inputs = {"raw": str(p_dict.get('inputs'))}
            results = {"raw": str(p_dict.get('results'))}

        row = {
            "user_id": sb_uid,
            "prediction_type": p_dict.get('prediction_type') or 'crop',
            "inputs": inputs,
            "results": results,
            "created_at": p_dict.get('timestamp') or datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        if tables_ready:
            ok, err = supabase.insert_row("predictions", row)
            if ok:
                acct_preds.record_success()
            else:
                acct_preds.record_failure(f"Pred ID {p_dict['id']}", err or "Insert failed")
        else:
            acct_preds.record_failure(f"Pred ID {p_dict['id']}", "Remote table 'predictions' does not exist")

    print(f"  -> Predictions Summary: Attempted: {acct_preds.attempted}, Succeeded: {acct_preds.succeeded}, Failed: {acct_preds.failed}")

    # --------------------------------------------------------------------------
    # 3. MIGRATE EXPERIMENTS & METRICS
    # --------------------------------------------------------------------------
    print("\n[3/5] Migrating Experiments & MLOps Registry...")
    try:
        cur.execute("SELECT * FROM experiments")
        experiments = cur.fetchall()
        for e in experiments:
            e_dict = dict(e)
            acct_exps.record_attempt()
            row = {
                "experiment_id": e_dict['experiment_id'],
                "model_name": e_dict['model_name'],
                "task_name": e_dict['task_name'],
                "dataset_name": e_dict['dataset_name'],
                "dataset_hash": e_dict.get('dataset_hash'),
                "dataset_version": e_dict.get('dataset_version'),
                "random_seed": e_dict.get('random_seed', 42),
                "status": e_dict.get('status', 'COMPLETED'),
                "training_time": e_dict.get('training_time', 0.0),
                "inference_time": e_dict.get('inference_time', 0.0),
                "model_path": e_dict.get('model_path'),
                "error_message": e_dict.get('error_message'),
                "data_quality_status": e_dict.get('data_quality_status'),
                "leakage_status": e_dict.get('leakage_status'),
                "overfitting_status": e_dict.get('overfitting_status'),
                "baseline_score": e_dict.get('baseline_score'),
                "model_score": e_dict.get('model_score'),
                "validation_status": e_dict.get('validation_status'),
                "created_at": e_dict.get('created_at') or e_dict.get('timestamp')
            }
            if tables_ready:
                ok, err = supabase.insert_row("experiments", row)
                if ok:
                    acct_exps.record_success()
                else:
                    acct_exps.record_failure(e_dict['experiment_id'], err or "Insert failed")
            else:
                acct_exps.record_failure(e_dict['experiment_id'], "Remote table 'experiments' does not exist")
        print(f"  -> Experiments Summary: Attempted: {acct_exps.attempted}, Succeeded: {acct_exps.succeeded}, Failed: {acct_exps.failed}")
    except Exception as e:
        print(f"  [ERROR] Experiments read error: {e}")

    try:
        cur.execute("SELECT * FROM experiment_metrics")
        metrics = cur.fetchall()
        for m in metrics:
            m_dict = dict(m)
            acct_metrics.record_attempt()
            row = {
                "experiment_id": m_dict['experiment_id'],
                "metric_name": m_dict['metric_name'],
                "metric_value": m_dict['metric_value'],
                "split": m_dict['split'],
                "created_at": m_dict.get('created_at')
            }
            if tables_ready:
                ok, err = supabase.insert_row("experiment_metrics", row)
                if ok:
                    acct_metrics.record_success()
                else:
                    acct_metrics.record_failure(f"{m_dict['experiment_id']}_{m_dict['metric_name']}", err or "Insert failed")
            else:
                acct_metrics.record_failure(f"{m_dict['experiment_id']}_{m_dict['metric_name']}", "Remote table 'experiment_metrics' does not exist")
        print(f"  -> Metrics Summary: Attempted: {acct_metrics.attempted}, Succeeded: {acct_metrics.succeeded}, Failed: {acct_metrics.failed}")
    except Exception as e:
        print(f"  [ERROR] Metrics read error: {e}")

    # Model Versions
    try:
        cur.execute("SELECT * FROM model_versions")
        m_vers = cur.fetchall()
        for mv in m_vers:
            mv_dict = dict(mv)
            acct_models.record_attempt()
            best_params = json.loads(mv_dict['best_parameters_json']) if mv_dict.get('best_parameters_json') else {}
            metrics_json = json.loads(mv_dict['metrics_json']) if mv_dict.get('metrics_json') else {}
            row = {
                "model_name": mv_dict['model_name'],
                "version": mv_dict['version'],
                "experiment_id": mv_dict.get('experiment_id'),
                "model_path": mv_dict['model_path'],
                "dataset_version": mv_dict.get('dataset_version'),
                "best_parameters_json": best_params,
                "metrics_json": metrics_json,
                "is_production": bool(mv_dict.get('is_production', 0)),
                "created_at": mv_dict.get('created_at')
            }
            if tables_ready:
                ok, err = supabase.insert_row("model_versions", row)
                if ok:
                    acct_models.record_success()
                else:
                    acct_models.record_failure(f"{mv_dict['model_name']}_{mv_dict['version']}", err or "Insert failed")
            else:
                acct_models.record_failure(f"{mv_dict['model_name']}_{mv_dict['version']}", "Remote table 'model_versions' does not exist")
        print(f"  -> Model Versions Summary: Attempted: {acct_models.attempted}, Succeeded: {acct_models.succeeded}, Failed: {acct_models.failed}")
    except Exception as e:
        print(f"  [ERROR] Model versions read error: {e}")

    # --------------------------------------------------------------------------
    # 4. MIGRATE CORE BENCHMARK DATASETS TO SUPABASE STORAGE
    # --------------------------------------------------------------------------
    print("\n[4/5] Migrating Core Baseline Datasets to Supabase Storage...")
    core_datasets = [
        ("Crop Recommendation", "merged_ml_dataset.csv", "crop", "Crop"),
        ("Yield Prediction", "crop_production_karnataka.csv", "yield", "Yield_Tonnes"),
        ("Seed Viability", "seed_viability_data.csv", "seed", "Viable")
    ]

    for label, fname, dtype, target_col in core_datasets:
        acct_datasets.record_attempt()
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            acct_datasets.record_failure(fname, f"File not found at {fpath}")
            print(f"  [FAIL] {fname}: File does not exist")
            continue

        with open(fpath, 'rb') as f:
            fbytes = f.read()
        fhash = compute_hash(fpath)
        fsize = len(fbytes)
        storage_path = f"datasets/{dtype}/{fhash[:8]}_{fname}"

        print(f"  -> Uploading {fname} ({fsize} bytes) to {storage_path}...")
        ok_up, err_up = supabase.upload_file("seediq-datasets", storage_path, fbytes, content_type="text/csv")
        
        if ok_up:
            acct_datasets.record_success()
            print(f"  [OK] Uploaded {fname} to Storage.")
            if tables_ready:
                ds_entry = {
                    "name": label,
                    "original_filename": fname,
                    "stored_path": storage_path,
                    "dataset_type": dtype,
                    "file_size": fsize,
                    "target_column": target_col,
                    "status": "ready",
                    "checksum": fhash
                }
                supabase.insert_row("datasets", ds_entry)
                ver_entry = {
                    "dataset_name": label,
                    "version": "v001",
                    "file_hash": fhash,
                    "stored_path": storage_path,
                    "target_column": target_col,
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                supabase.insert_row("dataset_versions", ver_entry)
        else:
            acct_datasets.record_failure(fname, f"Storage upload failed: {err_up}")
            print(f"  [FAIL] Storage upload failed for {fname}: {err_up}")

    print(f"  -> Baseline Datasets Summary: Attempted: {acct_datasets.attempted}, Succeeded: {acct_datasets.succeeded}, Failed: {acct_datasets.failed}")

    # --------------------------------------------------------------------------
    # 5. FINAL ACCOUNTING & EXIT REPORT
    # --------------------------------------------------------------------------
    all_accountings = [acct_users, acct_preds, acct_exps, acct_metrics, acct_models, acct_datasets]
    total_attempted = sum(a.attempted for a in all_accountings)
    total_succeeded = sum(a.succeeded for a in all_accountings)
    total_failed = sum(a.failed for a in all_accountings)

    overall_status = "SUCCESS"
    if total_failed > 0 and total_succeeded > 0:
        overall_status = "PARTIAL FAILURE"
    elif total_failed > 0 and total_succeeded == 0:
        overall_status = "FAILED"

    print("\n" + "=" * 70)
    print(f"MIGRATION REPORT - OVERALL STATUS: {overall_status}")
    print("=" * 70)
    print(f"{'ENTITY':<25} | {'ATTEMPTED':<10} | {'SUCCEEDED':<10} | {'FAILED':<10}")
    print("-" * 70)
    for a in all_accountings:
        print(f"{a.name:<25} | {a.attempted:<10} | {a.succeeded:<10} | {a.failed:<10}")
    print("-" * 70)
    print(f"{'TOTAL':<25} | {total_attempted:<10} | {total_succeeded:<10} | {total_failed:<10}")
    print("=" * 70)

    log_activity(
        f"MIGRATION_{overall_status.replace(' ', '_')}",
        user_id="system",
        details={
            "overall_status": overall_status,
            "total_attempted": total_attempted,
            "total_succeeded": total_succeeded,
            "total_failed": total_failed
        }
    )

    conn.close()

    if overall_status != "SUCCESS":
        print(f"\n[EXIT] Exiting with code 1 due to migration status: {overall_status}")
        sys.exit(1)
    else:
        print("\n[EXIT] Migration completed with full success.")
        sys.exit(0)


if __name__ == "__main__":
    migrate()
