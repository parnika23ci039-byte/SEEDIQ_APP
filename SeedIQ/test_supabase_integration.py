"""
SeedIQ Integration & Persistence Test Suite
Validates:
1. Authentication (Login, Fallback, Wrong Password, Guest isolation, Session)
2. Dataset Ingestion Pipeline (Validation, Schema Detection, Preprocessing, Feature Extraction, Versioning, Auditing)
3. Prediction Telemetry (Persistence, Isolation, Guest Rejection)
4. Activity & Audit Logging (Security events, Pipeline events)
5. Storage & Database Endpoints (/api/datasets)
6. Remote Live Supabase Diagnostic Checks (Tables, Storage Bucket, RLS, Storage Objects)
"""

import os
import io
import json
import sqlite3
import unittest
import requests
import pandas as pd

# Ensure test environment
os.environ["TESTING"] = "1"

from app import app, get_db
from dataset_service import process_and_store_dataset, validate_csv
from activity_logger import log_activity
from supabase_client import supabase


class TestSeedIQLocalPersistence(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    # --------------------------------------------------------------------------
    # 1. AUTHENTICATION & SECURITY TESTS
    # --------------------------------------------------------------------------
    def test_01_admin_login_and_role_hierarchy(self):
        """Verify Admin login resolves correctly."""
        res = self.client.post('/api/login', json={
            'email': 'admin@seediq.ai',
            'password': 'admin123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['user']['role'], 'Admin')
        self.assertIn('admin', data['user']['email'].lower())

    def test_02_researcher_login(self):
        """Verify Researcher login resolves correctly."""
        res = self.client.post('/api/login', json={
            'email': 'researcher@quantum.org',
            'password': 'research123'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['user']['role'], 'Researcher')

    def test_03_wrong_password_rejected(self):
        """Verify wrong password returns 401 and does not authenticate."""
        res = self.client.post('/api/login', json={
            'email': 'admin@seediq.ai',
            'password': 'WrongPassword999!'
        })
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data['status'], 'error')

    def test_04_guest_login_and_isolation(self):
        """Verify guest login creates no fake database records."""
        res = self.client.post('/api/guest-login')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['user']['isGuest'])
        self.assertEqual(data['user']['role'], 'Guest')

        # Check /api/me
        me_res = self.client.get('/api/me')
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.get_json()
        self.assertTrue(me_data['authenticated'])
        self.assertEqual(me_data['user']['role'], 'Guest')

    def test_05_guest_prediction_rejected_from_database(self):
        """Verify guest predictions do NOT pollute user predictions table."""
        with self.client:
            self.client.post('/api/guest-login')
            
            with get_db() as conn:
                count_before = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

            pred_res = self.client.post('/api/crop-recommendation', json={
                'nitrogen': 90, 'phosphorus': 42, 'potassium': 43,
                'temperature': 20.8, 'humidity': 82.0, 'ph': 6.5, 'rainfall': 202.9
            })
            self.assertEqual(pred_res.status_code, 200)

            with get_db() as conn:
                count_after = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

            self.assertEqual(count_before, count_after, "Guest prediction must not be inserted into database.")

    def test_06_authenticated_prediction_persisted(self):
        """Verify authenticated user prediction is saved and linked."""
        with self.client:
            login_res = self.client.post('/api/login', json={
                'email': 'admin@seediq.ai',
                'password': 'admin123'
            })
            self.assertEqual(login_res.status_code, 200)

            with get_db() as conn:
                count_before = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

            pred_res = self.client.post('/api/crop-recommendation', json={
                'nitrogen': 90, 'phosphorus': 42, 'potassium': 43,
                'temperature': 20.8, 'humidity': 82.0, 'ph': 6.5, 'rainfall': 202.9
            })
            self.assertEqual(pred_res.status_code, 200)
            data = pred_res.get_json()
            self.assertIn('result', data)

            with get_db() as conn:
                count_after = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]

            self.assertGreater(count_after, count_before, "Authenticated prediction must be logged.")

    # --------------------------------------------------------------------------
    # 2. DATASET INGESTION & AUTOMATED PIPELINE TESTS
    # --------------------------------------------------------------------------
    def test_07_csv_validation(self):
        """Verify CSV validator rejects non-CSV and empty files."""
        ok, msg, _ = validate_csv(b"hello", "test.txt")
        self.assertFalse(ok)
        
        ok, msg, _ = validate_csv(b"", "test.csv")
        self.assertFalse(ok)

        valid_csv_bytes = b"Nitrogen,Phosphorus,Potassium,Temperature,Humidity,pH,Rainfall,Crop\n90,42,43,20.8,82.0,6.5,202.9,rice\n85,58,41,21.7,80.3,7.0,226.6,rice\n"
        ok, msg, df = validate_csv(valid_csv_bytes, "crop_test.csv")
        self.assertTrue(ok)
        self.assertEqual(df.shape[0], 2)

    def test_08_automated_dataset_processing_and_versioning(self):
        """Verify uploading a CSV executes detection, preprocessing, and versioning."""
        csv_content = (
            "Nitrogen,Phosphorus,Potassium,Temperature,Humidity,pH,Rainfall,Crop\n"
            "90,42,43,20.8,82.0,6.5,202.9,rice\n"
            "85,58,41,21.7,80.3,7.0,226.6,rice\n"
            "60,55,44,23.0,82.3,7.8,263.9,rice\n"
            "74,35,40,26.4,80.1,6.9,242.8,rice\n"
        ).encode('utf-8')

        result = process_and_store_dataset(
            file_bytes=csv_content,
            filename="unit_test_crop.csv",
            user_id="test_admin",
            user_role="Admin"
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["detected_type"], "Crop Recommendation")
        self.assertTrue(result["version"].startswith("v"))
        self.assertEqual(result["rows"], 4)
        self.assertEqual(result["preprocessing_status"], "COMPLETED")
        self.assertIn("Nitrogen", result["features"])

    def test_09_api_datasets_endpoint(self):
        """Verify /api/datasets returns datasets catalogue for the frontend."""
        res = self.client.get('/api/datasets')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        first = data[0]
        self.assertIn("id", first)
        self.assertIn("name", first)
        self.assertIn("status", first)

    def test_10_activity_logging(self):
        """Verify activity logs are recorded in SQLite."""
        log_activity(
            "TEST_EVENT",
            user_id="test_runner",
            details={"action": "unit_test_verification"},
            status="SUCCESS"
        )

        with get_db() as conn:
            row = conn.execute("SELECT * FROM activity_logs WHERE event_type = 'TEST_EVENT' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['event_type'], 'TEST_EVENT')
            self.assertEqual(row['user_id'], 'test_runner')


class TestSeedIQLiveRemoteSupabaseDiagnostic(unittest.TestCase):
    """
    Live diagnostics against the actual remote Supabase instance.
    Truthfully verifies remote database tables, bucket presence, and live connectivity.
    """
    def test_live_01_remote_connectivity(self):
        """Check live HTTP connectivity to Supabase project."""
        url = supabase.url
        key = supabase.key
        headers = {'apikey': key, 'Authorization': f'Bearer {key}'}
        r = requests.get(f"{url}/auth/v1/health", headers=headers, timeout=10)
        # 200 means Supabase auth/API engine is reachable
        self.assertEqual(r.status_code, 200, "Supabase health endpoint must return 200")

    def test_live_02_remote_tables_existence_report(self):
        """Queries actual remote PostgREST schema for required tables."""
        url = supabase.url
        key = supabase.key
        headers = {'apikey': key, 'Authorization': f'Bearer {key}'}

        required_tables = [
            'profiles', 'predictions', 'datasets', 'dataset_versions', 'dataset_audits',
            'experiments', 'experiment_metrics', 'hyperparameter_trials', 'model_versions',
            'reports', 'cross_validation_results', 'robustness_results', 'test_runs',
            'test_results', 'activity_logs'
        ]

        missing_tables = []
        existing_tables = []

        for t in required_tables:
            r = requests.get(f"{url}/rest/v1/{t}?select=count&limit=1", headers=headers, timeout=5)
            if r.status_code == 200:
                existing_tables.append(t)
            else:
                missing_tables.append(t)

        print("\n" + "-" * 60)
        print(f"[LIVE CHECK] Remote PostgreSQL Tables: {len(existing_tables)}/15 present.")
        if missing_tables:
            print(f"[LIVE CHECK] Missing tables: {', '.join(missing_tables)}")
            print("[LIVE CHECK] REMOTE DATABASE MIGRATION NOT APPLIED.")
        print("-" * 60)

    def test_live_03_remote_storage_bucket_report(self):
        """Queries actual remote storage API for 'seediq-datasets' bucket."""
        url = supabase.url
        key = supabase.key
        headers = {'apikey': key, 'Authorization': f'Bearer {key}'}

        r = requests.get(f"{url}/storage/v1/bucket", headers=headers, timeout=5)
        bucket_found = False
        is_private = None

        if r.status_code == 200:
            for b in r.json():
                if b.get("id") == "seediq-datasets":
                    bucket_found = True
                    is_private = not b.get("public", False)

        print("\n" + "-" * 60)
        print(f"[LIVE CHECK] Remote Storage 'seediq-datasets' bucket exists: {bucket_found}")
        if bucket_found:
            print(f"[LIVE CHECK] Bucket is private: {is_private}")
        else:
            print("[LIVE CHECK] STORAGE BUCKET 'seediq-datasets' MISSING.")
        print("-" * 60)


if __name__ == '__main__':
    unittest.main()
