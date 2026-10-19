#!/usr/bin/env python3
"""SeedIQ Phase 1/2 baseline inventory — datasets, trained artifacts, active wiring.

Read-only. Nothing here writes to data/ or models/. It records the freeze
baseline that Phase 8 compares against:

  * every dataset under SeedIQ/data: SHA-256, size, rows/cols, missing cells,
    target distribution for the labelled ones
  * every trained artifact under SeedIQ/models: SHA-256, size, mtime
  * which artifacts the production code actually loads (traced, not guessed)

Usage:
    .freebuff/venv/bin/python experiments/client_model_audit/baseline_inventory.py \
        experiments/client_model_audit/baseline_manifest.json
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEEDIQ = os.path.join(ROOT, "SeedIQ")

# Traced from SeedIQ/app.py (constants + load_helper call sites), not inferred
# from the directory listing. See baseline audit report §4.
ACTIVE_ARTIFACTS = {
    "crop_classical": "models/rf_model.pkl",
    "crop_scaler": "models/crop_scaler.pkl",
    "crop_encoder": "models/crop_encoder.pkl",
    "crop_quantum_vqc": "models/vqc_crop_model.pkl",
    "yield_classical": "models/yield_prediction/randomforest_model.pkl",
    "yield_contract_manifest": "models/yield_feature_manifest.json",
    "yield_quantum_vqc": "models/vqc_yield_model.pkl",
    "seed_classical": "models/seed_viability/randomforest_model.pkl",
    "seed_scaler": "models/seed_scaler.pkl",
    "seed_quantum_vqc": "models/vqc_seed_model.pkl",
    "meta_stacking": "models/meta_model.pkl",
}

# Present on disk, never loaded by app.py inference paths (verified by grep).
INACTIVE_ARTIFACTS = {
    "xgb_classical_legacy": "models/xgb_model.pkl",
    "svm_legacy": "models/svm_model.pkl",
    "vqc_legacy_uncontracted": "models/vqc_model.pkl",
    "crop_recommendation_rf": "models/crop_recommendation/randomforest_model.pkl",
    "experimental_district_yield": "models/experimental/district_yield_model.pkl",
    "yield_scaler_legacy": "models/yield_scaler.pkl",
    "yield_crop_encoder_legacy": "models/yield_crop_encoder.pkl",
    "yield_season_encoder_legacy": "models/yield_season_encoder.pkl",
}

ACTIVE_DATASETS = {
    "crop_train": "data/Crop_recommendation.csv",
    "yield_train": "data/yield_icrisat_karnataka.csv",
    "yield_source_icrisat": "data/ICRISAT-District Level Data.csv",
    "seed_train": "data/seed_viability_data.csv",
    "seed_real_unused": "data/Seed_Data.csv",
}

TARGET_HINTS = ("viab", "target", "label", "class", "yield", "production")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def describe_csv(path):
    import pandas as pd
    info = {}
    try:
        df = pd.read_csv(path)
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"
        return info
    info["rows"] = int(df.shape[0])
    info["columns"] = int(df.shape[1])
    info["column_names"] = list(df.columns)[:40]
    info["missing_cells"] = int(df.isna().sum().sum())
    info["duplicate_rows"] = int(df.duplicated().sum())
    info["memory_bytes"] = int(df.memory_usage(deep=True).sum())
    # target distribution: last column + anything that looks like a target
    for col in list(df.columns):
        if any(h in str(col).lower() for h in TARGET_HINTS):
            vc = df[col].value_counts(dropna=False)
            info.setdefault("target_distributions", {})[str(col)] = {
                str(k): int(v) for k, v in vc.head(12).items()
            }
    return info


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "baseline_manifest.json"
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": ROOT,
        "seed_hash_algorithm": "sha256",
        "active_artifacts": {},
        "inactive_artifacts": {},
        "datasets": {},
        "other_datasets": {},
        "code_fingerprints": {},
    }

    def record(bucket, name, rel):
        path = os.path.join(SEEDIQ, rel)
        entry = {"path": rel}
        if not os.path.exists(path):
            entry["present"] = False
            manifest[bucket][name] = entry
            return
        st = os.stat(path)
        entry.update({
            "present": True,
            "size_bytes": st.st_size,
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
            "sha256": sha256_file(path),
        })
        if rel.endswith(".csv") or rel.endswith(".json"):
            if rel.endswith(".csv"):
                entry.update(describe_csv(path))
            else:
                try:
                    with open(path) as f:
                        entry["json_keys"] = sorted(json.load(f).keys())
                except Exception as e:
                    entry["error"] = str(e)
        manifest[bucket][name] = entry
        print(f"  {bucket:<18} {name:<28} {entry.get('sha256','')[:16]}  {rel}")

    print("== ACTIVE (loaded by app.py) ==")
    for name, rel in ACTIVE_ARTIFACTS.items():
        record("active_artifacts", name, rel)
    print("== INACTIVE (on disk, not loaded) ==")
    for name, rel in INACTIVE_ARTIFACTS.items():
        record("inactive_artifacts", name, rel)
    print("== DATASETS (named in code) ==")
    for name, rel in ACTIVE_DATASETS.items():
        record("datasets", name, rel)

    print("== DATASETS (rest of data/) ==")
    data_dir = os.path.join(SEEDIQ, "data")
    known = set(ACTIVE_DATASETS.values())
    for fn in sorted(os.listdir(data_dir)):
        rel = f"data/{fn}"
        if rel in known or not os.path.isfile(os.path.join(data_dir, fn)):
            continue
        if not fn.lower().endswith((".csv", ".xlsx")):
            continue
        st = os.stat(os.path.join(data_dir, fn))
        e = {"path": rel, "size_bytes": st.st_size,
             "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
             "sha256": sha256_file(os.path.join(data_dir, fn))}
        if fn.lower().endswith(".csv"):
            try:
                e.update(describe_csv(os.path.join(data_dir, fn)))
            except Exception as exc:
                e["error"] = str(exc)
        manifest["other_datasets"][fn] = e

    print("== CODE FINGERPRINTS ==")
    for rel in ("SeedIQ/app.py", "SeedIQ/phone_auth.py", "SeedIQ/train_all_models.py",
                "SeedIQ/seed_viability_semantics.py", "SeedIQ/yield_semantics.py",
                "SeedIQ/qml_model.py", "SeedIQ/yield_model.py",
                "SeedIQ/training_registry.json", "SeedIQ/requirements.txt"):
        path = os.path.join(ROOT, rel)
        if os.path.exists(path):
            st = os.stat(path)
            manifest["code_fingerprints"][rel] = {
                "size_bytes": st.st_size,
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256_file(path),
            }
            print(f"  {rel:<44} {manifest['code_fingerprints'][rel]['sha256'][:16]}")

    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f"\nwrote {out_path}")
    print(f"datasets frozen: {len(manifest['datasets']) + len(manifest['other_datasets'])} | "
          f"active artifacts: {len(manifest['active_artifacts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
