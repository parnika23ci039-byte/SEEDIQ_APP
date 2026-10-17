import numpy as np
import pickle
import os
from sklearn.linear_model import LogisticRegression

# ---------------------------------------------------------------------------
# DEMO / TEACHING NOTEBOOK — NOT PART OF THE PRODUCTION PIPELINE.
#
# This notebook trains on RANDOM arrays, so nothing it produces is a real model.
# It previously did two harmful things:
#   * it overwrote models/meta_model.pkl with a LogisticRegression fitted on
#     random 80x4 data, destroying the real stacked meta model the API serves
#     (and producing exactly the "meta collapsed to the majority class" symptom
#     this project had to fix);
#   * it overwrote models/vqc_model.pkl with the literal string
#     "Mock VQC Object";
#   * it printed a fabricated "Hybrid Quantum Meta-Model Accuracy: 96.1%".
#
# Writes are now opt-in via SEEDIQ_ALLOW_DEMO_ARTIFACT_OVERWRITE=1, and no
# accuracy is reported, because a score computed on random data means nothing.
# The real training path is:  python train_all_models.py
# ---------------------------------------------------------------------------

# Note: in a real Google Colab environment, you would run:
# !pip install qiskit qiskit-machine-learning

print("--- DEMO: Quantum ML & Meta Model scaffolding (random data) ---")
print("Setting up Qiskit VQC Environment...")

DEMO_FORCE = os.environ.get("SEEDIQ_ALLOW_DEMO_ARTIFACT_OVERWRITE", "").strip().lower() in (
    "1", "true", "yes", "on")

os.makedirs("models", exist_ok=True)


def write_demo_artifact(obj, path):
    """Write a demo object only if it would not clobber a trained artifact."""
    if os.path.exists(path) and not DEMO_FORCE:
        print(f"SKIPPED {path}: a trained artifact already exists and was NOT overwritten "
              f"(set SEEDIQ_ALLOW_DEMO_ARTIFACT_OVERWRITE=1 to force). "
              f"Use train_all_models.py to regenerate real models.")
        return False
    with open(path, "wb") as handle:
        pickle.dump(obj, handle)
    print(f"Wrote DEMO object to {path} (trained on random data — not a real model).")
    return True


try:
    from qiskit.circuit.library import ZZFeatureMap, RealAmplitudes
    from qiskit_machine_learning.algorithms.classifiers import VQC
    from qiskit.primitives import Sampler

    # Demonstration wiring only — the data below is random, not agricultural.
    print("Initializing Quantum Feature Map and Ansatz...")
    feature_map = ZZFeatureMap(feature_dimension=2, reps=1)
    ansatz = RealAmplitudes(num_qubits=2, reps=1)

    sampler = Sampler()
    vqc = VQC(feature_map=feature_map, ansatz=ansatz, optimizer=None, sampler=sampler)

    # Random demo data for the VQC scaffold
    X_train_vqc = np.random.rand(20, 2)
    y_train_vqc = np.random.randint(0, 2, 20)

    print("Fitting the VQC scaffold on random demo data...")
    vqc.fit(X_train_vqc, y_train_vqc)
    print("Demo VQC fit complete (random data — not a trained production model).")

except ImportError:
    print("Qiskit is not installed. This notebook does not install it; the production "
          "quantum path is the PennyLane/sklearn simulated implementation in qml_model.py.")

# 4. Meta Model scaffolding (random demo data)
print("Building a Logistic Regression scaffold for the meta stage...")
meta_model = LogisticRegression()
# In the real pipeline, X_meta is the out-of-fold prediction matrix built by
# train_all_models.py from crop/yield/seed OOF outputs.
X_meta = np.random.rand(80, 4)
y_meta = np.random.randint(0, 2, 80)
meta_model.fit(X_meta, y_meta)

write_demo_artifact(meta_model, "models/meta_model.pkl")
write_demo_artifact("Mock VQC Object", "models/vqc_model.pkl")

print("Demo export step complete.")
print("No accuracy is reported here: this notebook trains on random arrays, so any "
      "score would be meaningless. Run train_all_models.py for measured metrics.")
