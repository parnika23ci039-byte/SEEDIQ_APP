import pytest
import os
import sys
import numpy as np
import pandas as pd

# Add SeedIQ path
sys.path.insert(0, os.path.dirname(__file__))

from data_validator import run_data_quality_checks, run_data_leakage_checks
from experiment_tracker import init_experiment_db, get_db_connection
from data_preprocessing import preprocess_crop_data, preprocess_yield_data, preprocess_seed_data
import app

# 1. Data Quality Tests
def test_data_quality_crop():
    # The real crop training set is Crop_recommendation.csv (2200 records, target
    # `label`). `merged_ml_dataset.csv` is only a tiny checked-in sample, so
    # auditing it reported "Target column 'Crop' missing" and always failed.
    rep = run_data_quality_checks('data/Crop_recommendation.csv', 'label')
    assert rep["exists"] is True
    assert rep["not_empty"] is True
    assert rep["passed"] is True

def test_data_quality_yield():
    rep = run_data_quality_checks('data/crop_production_karnataka.csv', 'Yield_Tonnes')
    assert rep["exists"] is True
    assert rep["not_empty"] is True
    assert rep["passed"] is True

def test_data_quality_seed():
    rep = run_data_quality_checks('data/seed_viability_data.csv', 'Viable')
    assert rep["exists"] is True
    assert rep["not_empty"] is True
    assert rep["passed"] is True

# 2. Data Leakage Test
def test_no_data_leakage():
    X_train = np.array([[1, 2], [3, 4], [5, 6]])
    X_test = np.array([[7, 8], [9, 10]])
    leak_rep = run_data_leakage_checks(X_train, X_test, None, None)
    assert leak_rep["passed"] is True
    assert leak_rep["duplicate_rows_between_splits"] == 0

# 3. Preprocessing Tests
def test_preprocess_crop_data():
    X_scaled, y, scaler, crop_encoder = preprocess_crop_data('data/Crop_recommendation.csv')
    assert X_scaled.shape[0] > 0
    assert X_scaled.shape[1] == 7
    assert len(y) == X_scaled.shape[0]

def test_preprocess_yield_data():
    X_scaled, y, scaler, crop_enc, season_enc = preprocess_yield_data('data/crop_production_karnataka.csv')
    assert X_scaled.shape[0] > 0
    assert X_scaled.shape[1] == 5
    assert len(y) == X_scaled.shape[0]

# 4. Database Tests
def test_database_tables():
    init_experiment_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        assert "experiments" in tables
        assert "experiment_metrics" in tables
        assert "dataset_versions" in tables
        assert "model_versions" in tables

# 5. Flask API Route Tests
@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    with app.app.test_client() as client:
        yield client

def test_weather_api(client):
    rv = client.get('/api/weather/Belagavi')
    assert rv.status_code == 200
    json_data = rv.get_json()
    assert "temp" in json_data
    assert "hum" in json_data
    assert "rain" in json_data
