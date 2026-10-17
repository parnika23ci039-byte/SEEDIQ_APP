# Simplified QML using PennyLane
try:
    import pennylane as qml
    from pennylane import numpy as pnp
    PENNYLANE_AVAILABLE = True
except ImportError:
    PENNYLANE_AVAILABLE = False

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.linear_model import RidgeClassifier, Ridge

if PENNYLANE_AVAILABLE:
    n_qubits = 2
    dev = qml.device("default.qubit", wires=n_qubits)

    @qml.qnode(dev)
    def circuit(params, x):
        for i in range(n_qubits):
            qml.RY(x[i], wires=i)
        for i in range(n_qubits):
            qml.RZ(params[i], wires=i)
        return [qml.expval(qml.PauliZ(i)) for i in range(n_qubits)]

    def qml_predict(params, x):
        return circuit(params, x)
else:
    def qml_predict(params, x):
        return np.zeros(2)

# --- Shared Simulated Quantum Machine Learning Fallback Classes ---
class SimulatedQuantumClassifier(ClassifierMixin, BaseEstimator):
    _estimator_type = "classifier"

    def __init__(self, n_components=12, alpha=0.001, epochs=100):
        self.n_components = n_components
        self.alpha = alpha
        self.epochs = epochs
        from sklearn.linear_model import SGDClassifier
        self.classifier = SGDClassifier(
            loss='log_loss', alpha=self.alpha, random_state=42,
            learning_rate='adaptive',
            eta0=0.01,
            class_weight='balanced'
        )
        self.projection_matrix = None
        
    def _quantum_feature_map(self, X):
        if hasattr(X, "to_numpy"):
            X_arr = X.to_numpy(dtype=np.float64)
        else:
            X_arr = np.asarray(X, dtype=np.float64)

        if self.projection_matrix is None:
            rng = np.random.default_rng(seed=99)
            self.projection_matrix = rng.normal(size=(X_arr.shape[1], self.n_components))
            
        projected = X_arr @ self.projection_matrix
        features = []
        for i in range(self.n_components):
            features.append(np.sin(projected[:, i]))
            features.append(np.cos(projected[:, i]))
            features.append(np.sin(2.0 * projected[:, i]))
            features.append(np.cos(2.0 * projected[:, i]))
        return np.column_stack(features)

    def __sklearn_is_fitted__(self):
        return hasattr(self, "is_fitted_") and self.is_fitted_

    def fit(self, X, y):
        X_q = self._quantum_feature_map(X)
        self.classes_ = np.unique(y)
        self.classifier.fit(X_q, y)
        self.is_fitted_ = True
        return self
        
    def predict(self, X):
        X_q = self._quantum_feature_map(X)
        return self.classifier.predict(X_q)
        
    def predict_proba(self, X):
        X_q = self._quantum_feature_map(X)
        dec = self.classifier.decision_function(X_q)
        if len(self.classes_) == 2:
            probs = 1 / (1 + np.exp(-dec))
            return np.column_stack((1 - probs, probs))
        else:
            e_dec = np.exp(dec - np.max(dec, axis=1, keepdims=True))
            return e_dec / np.sum(e_dec, axis=1, keepdims=True)

class SimulatedQuantumRegressor(RegressorMixin, BaseEstimator):
    _estimator_type = "regressor"

    def __init__(self, n_components=8, alpha=0.01, epochs=100):
        self.n_components = n_components
        self.alpha = alpha
        self.epochs = epochs
        from sklearn.ensemble import GradientBoostingRegressor
        # Maximize score: tie n_estimators to epochs and increase tree depth
        self.regressor = GradientBoostingRegressor(
            n_estimators=self.epochs * 2, 
            max_depth=5, 
            learning_rate=0.1, 
            random_state=42
        )
        self.projection_matrix = None
        
    def _quantum_feature_map(self, X, fit=False):
        if hasattr(X, "to_numpy"):
            X_arr = X.to_numpy(dtype=np.float64)
        else:
            X_arr = np.asarray(X, dtype=np.float64)

        if self.projection_matrix is None:
            rng = np.random.default_rng(seed=99)
            self.projection_matrix = rng.normal(size=(X_arr.shape[1], self.n_components))

        projected = X_arr @ self.projection_matrix

        # Rescaling must use the statistics of the training population. Deriving
        # them from the batch being transformed made a single-row prediction
        # divide by a standard deviation of zero, so inference values exploded
        # (a 60 t/ha plot was predicted at 247 t/ha) even though training looked
        # healthy. The scale is therefore captured at fit time and reused.
        if fit or getattr(self, "proj_scale_", None) is None:
            self.proj_scale_ = np.std(projected, axis=0) + 1e-8
        projected = projected / self.proj_scale_
        
        # Include original features to preserve the linear relationship (Crucial for Yield ~ Area)
        features = [X_arr]
        for i in range(self.n_components):
            features.append(np.sin(projected[:, i]))
            features.append(np.cos(projected[:, i]))
            features.append(np.sin(2.0 * projected[:, i]))
            features.append(np.cos(2.0 * projected[:, i]))
            features.append(projected[:, i] ** 2)
        return np.column_stack(features)
        
    def __sklearn_is_fitted__(self):
        return hasattr(self, "is_fitted_") and self.is_fitted_

    def fit(self, X, y):
        X_q = self._quantum_feature_map(X, fit=True)
        self.regressor.fit(X_q, y)
        self.is_fitted_ = True
        return self
        
    def predict(self, X):
        X_q = self._quantum_feature_map(X)
        return self.regressor.predict(X_q)

