#!/usr/bin/env python3
"""Verify every saved meta-model candidate through its real load interface.

  * loads each artifact from disk,
  * re-scores it on the CANONICAL frozen 440 test rows,
  * checks the reloaded confusion matrix / balanced accuracy / macro-F1 against
    the values stored inside the artifact,
  * asserts both experiment caches describe the SAME test row set (same labels,
    same 6-feature matrix), so cross-script comparisons are valid.

Exit status is the source of truth (0 = all pass).
"""
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             confusion_matrix, f1_score)

AUD = Path(__file__).resolve().parent


def sha16(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()[:16]


z_push = np.load(AUD / "meta_push_final_cache.npz")
z_root = np.load(AUD / "meta_root_cause_cache.npz")

print("=" * 78)
print("ROW-SET IDENTITY — both experiment caches must describe the same rows")
print("=" * 78)
same_labels = np.array_equal(z_push["y_te"], z_root["te_y"])
same_feats = np.allclose(z_push["X_te"][:, :6], z_root["te_X"][:, :6])
print(f"  push cache test labels sha16 : {sha16(z_push['y_te'])}")
print(f"  root cache test labels sha16 : {sha16(z_root['te_y'])}")
print(f"  identical labels = {same_labels} | identical 6-feature rows = {same_feats}")
if not (same_labels and same_feats):
    print("ROW-SET IDENTITY: FAIL — candidates are not comparable")
    sys.exit(1)

y_te = z_push["y_te"]
X6 = z_push["X_te"][:, :6]
X11 = z_push["X_te"][:, :11]
X16 = z_push["X_te"]
n = len(y_te)
maj = max(float(y_te.mean()), 1 - float(y_te.mean()))
print(f"\ncanonical frozen test rows = {n} | success={int((y_te == 1).sum())} "
      f"failure={int((y_te == 0).sum())} | majority = {maj*100:.2f}%\n")

# artifact -> (feature matrix, expected accuracy, expected correct count)
CASES = {
    "meta_model_candidate_lr_6feat_dropin.pkl": (X6, 0.5954545454545455, 262),
    "meta_model_candidate_gbm_dropin.pkl": (X6, 0.6045454545454545, 266),
    "meta_model_candidate_gbm_11feat.pkl": (X11, 0.6068181818181818, 267),
}

all_ok = True
print("=" * 78)
print("ARTIFACT RELOAD + RE-SCORE")
print("=" * 78)
for name, (Xsrc, exp_acc, exp_n) in CASES.items():
    path = AUD / "models" / name
    if not path.exists():
        print(f"{name}: MISSING")
        all_ok = False
        continue
    with open(path, "rb") as f:
        art = pickle.load(f)
    cols = art.get("feature_index", list(range(art["n_features"])))
    thr = art.get("threshold")
    thr = 0.5 if thr is None else thr
    proba = art["estimator"].predict_proba(Xsrc[:, cols])[:, 1]
    pred = (proba >= thr).astype(int)
    acc = float(accuracy_score(y_te, pred))
    n_correct = int((pred == y_te).sum())
    bal = float(balanced_accuracy_score(y_te, pred))
    f1 = float(f1_score(y_te, pred, average="macro", zero_division=0))
    cm = confusion_matrix(y_te, pred).tolist()

    checks = {
        "matches expected accuracy": abs(acc - exp_acc) < 1e-12,
        "matches expected correct count": n_correct == exp_n,
        "matches its own stored accuracy": abs(acc - art["test_accuracy"]) < 1e-12,
        "feature_names length == n_features": len(art["feature_names"]) == art["n_features"],
    }
    # only assert metadata the artifact actually carries
    notes = []
    for key, got in (("confusion_matrix", cm), ("balanced_accuracy", bal),
                     ("macro_f1", f1), ("n_test", n), ("n_correct", n_correct)):
        if key in art:
            checks[f"stored {key} reproduced"] = (
                abs(float(art[key]) - float(got)) < 1e-9 if isinstance(got, float)
                else art[key] == got)
        else:
            notes.append(f"(artifact stores no '{key}' — not asserted)")
    good = all(checks.values())
    all_ok &= good
    print(f"\n{name}")
    print(f"  features={art['n_features']} ({art.get('feature_set','?')})  thr={thr:.3f}  "
          f"drop_in={art.get('drop_in_replaces_meta_model_pkl')}")
    print(f"  reloaded accuracy={acc*100:.2f}% ({n_correct}/{n})  balanced={bal*100:.2f}%  "
          f"macroF1={f1*100:.2f}%")
    print(f"  confusion_matrix={cm}")
    for k, v in checks.items():
        if not v:
            print(f"  !! FAILED: {k}")
    for nt in notes:
        print(f"  note: {nt}")
    print(f"  -> {'PASS' if good else 'FAIL'}")

    # keep the stored expectation honest if the source file ever drifts
    if not good:
        print(f"     stored: acc={art['test_accuracy']:.6f} cm={art.get('confusion_matrix')}")

print("\n" + "=" * 78)
print("VERIFICATION:", "PASS" if all_ok else "FAIL")
sys.exit(0 if all_ok else 1)
