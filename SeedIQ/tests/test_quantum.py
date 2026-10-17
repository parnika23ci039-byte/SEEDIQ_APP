import pytest
import numpy as np
import pandas as pd
import os
import sys

# Ensure SeedIQ parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from qml_model import SimulatedQuantumClassifier, SimulatedQuantumRegressor

@pytest.fixture
def dummy_classification_data():
    rng = np.random.default_rng(42)
    X_arr = rng.normal(size=(50, 6))
    y_arr = rng.choice([0, 1], size=50)
    df_X = pd.DataFrame(X_arr, columns=[f"feat_{i}" for i in range(6)])
    return X_arr, df_X, y_arr

@pytest.fixture
def dummy_regression_data():
    rng = np.random.default_rng(42)
    X_arr = rng.normal(size=(50, 5))
    y_arr = X_arr[:, 0] * 2.5 + rng.normal(scale=0.1, size=50)
    df_X = pd.DataFrame(X_arr, columns=[f"col_{i}" for i in range(5)])
    return X_arr, df_X, y_arr

def test_qml_classifier_ndarray(dummy_classification_data):
    X_arr, _, y_arr = dummy_classification_data
    clf = SimulatedQuantumClassifier(n_components=6)
    clf.fit(X_arr, y_arr)
    preds = clf.predict(X_arr)
    probs = clf.predict_proba(X_arr)
    
    assert len(preds) == len(y_arr)
    assert not np.isnan(preds).any()
    assert not np.isinf(preds).any()
    assert probs.shape == (50, 2)
    assert not np.isnan(probs).any()

def test_qml_classifier_dataframe(dummy_classification_data):
    _, df_X, y_arr = dummy_classification_data
    clf = SimulatedQuantumClassifier(n_components=6)
    # Must not raise KeyError: (slice(None, None, None), 0)
    clf.fit(df_X, y_arr)
    preds = clf.predict(df_X)
    probs = clf.predict_proba(df_X)
    
    assert len(preds) == len(y_arr)
    assert not np.isnan(preds).any()
    assert not np.isinf(preds).any()
    assert probs.shape == (50, 2)
    assert not np.isnan(probs).any()

def test_qml_regressor_ndarray(dummy_regression_data):
    X_arr, _, y_arr = dummy_regression_data
    reg = SimulatedQuantumRegressor(n_components=6)
    reg.fit(X_arr, y_arr)
    preds = reg.predict(X_arr)
    
    assert len(preds) == len(y_arr)
    assert not np.isnan(preds).any()
    assert not np.isinf(preds).any()

def test_qml_regressor_dataframe(dummy_regression_data):
    _, df_X, y_arr = dummy_regression_data
    reg = SimulatedQuantumRegressor(n_components=6)
    # Must not raise KeyError: (slice(None, None, None), 0)
    reg.fit(df_X, y_arr)
    preds = reg.predict(df_X)
    
    assert len(preds) == len(y_arr)
    assert not np.isnan(preds).any()
    assert not np.isinf(preds).any()
