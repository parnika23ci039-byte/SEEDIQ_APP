"""
Field-Level Dataset Audit
=========================
Systematically inspects every dataset in SeedIQ/data/ and classifies it as:
  - DISTRICT_LEVEL   : aggregate statistics, not usable for field prediction
  - FIELD_CANDIDATE  : has individual-plot/field rows worth evaluating
  - INCOMPATIBLE     : no yield target, wrong domain, or synthetic
  - SYNTHETIC        : detectably augmented or generated

Run:
    python3 experiments/ml_optimization/field_level/01_dataset_audit.py

Output written to:
    experiments/ml_optimization/field_level/dataset_audit_results.json
"""

import csv
import json
import os
import statistics
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent.parent / "SeedIQ" / "data"
OUT_PATH = Path(__file__).parent / "dataset_audit_results.json"

DATASETS = {
    "ICRISAT-District Level Data.csv": {
        "expected_granularity": "DISTRICT_LEVEL",
        "yield_col": None,
        "notes": "District-level annual totals for Karnataka 2000-2017. "
                 "Area in 1000-ha, production in 1000-tons. "
                 "Not usable for individual field prediction."
    },
    "yield_icrisat_karnataka.csv": {
        "expected_granularity": "DISTRICT_LEVEL",
        "yield_col": "Yield_Tonnes",
        "notes": "Derived from ICRISAT-DLD: one row = one district × crop × year. "
                 "Yield_Tonnes is total district production (tens of thousands of tonnes). "
                 "NOT per-hectare field yield. Current production model uses this."
    },
    "Crop Yiled with Soil and Weather.csv": {
        "expected_granularity": "FIELD_CANDIDATE",
        "yield_col": "yeild",
        "notes": "Has N, P, K, Fertilizer, temp, yield. No crop type, no location, "
                 "no date. Yield 5-12 range suggests t/ha for a single unnamed crop. "
                 "Partially real data (first ~1000 rows) + GAN/augmentation artifacts visible."
    },
    "Soil-Climate-data.csv": {
        "expected_granularity": "INCOMPATIBLE",
        "yield_col": None,
        "notes": "Binary classification target 'Compatible'. No yield in t/ha. "
                 "10,000 rows with farm-level soil and climate inputs. "
                 "Usable for crop-soil suitability, not yield prediction."
    },
    "Train Dataset.csv": {
        "expected_granularity": "INCOMPATIBLE",
        "yield_col": None,
        "notes": "NPK + pH + rainfall + temperature → Crop class. "
                 "Same schema as Crop_recommendation.csv but 18,079 rows (duplicated). "
                 "Crop recommendation dataset, no yield."
    },
    "Test Dataset.csv": {
        "expected_granularity": "INCOMPATIBLE",
        "yield_col": None,
        "notes": "Identical schema to Train Dataset.csv (18,079 rows). "
                 "Likely same dataset split – or same file entirely. "
                 "No yield target."
    },
    "Crop_recommendation.csv": {
        "expected_granularity": "INCOMPATIBLE",
        "yield_col": None,
        "notes": "2,200 rows, NPK/pH/rainfall/temp → crop label. "
                 "Standard Kaggle crop recommendation dataset. No yield."
    },
    "merged_ml_dataset.csv": {
        "expected_granularity": "INCOMPATIBLE",
        "yield_col": None,
        "notes": "Only 2 data rows. Same NPK schema. Not usable."
    },
    "crop_production_karnataka.csv": {
        "expected_granularity": "DISTRICT_LEVEL",
        "yield_col": None,
        "notes": "Karnataka crop production totals. Likely district-level aggregate."
    },
}


def audit_file(fname, meta):
    fpath = DATA_DIR / fname
    if not fpath.exists():
        return {"status": "FILE_NOT_FOUND", **meta}

    size_kb = fpath.stat().st_size // 1024
    try:
        with open(fpath, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            cols = list(reader.fieldnames or [])
            rows = list(reader)
    except Exception as e:
        return {"status": f"READ_ERROR: {e}", **meta}

    result = {
        "file": fname,
        "size_kb": size_kb,
        "n_rows": len(rows),
        "columns": cols,
        "expected_granularity": meta["expected_granularity"],
        "notes": meta["notes"],
    }

    ycol = meta.get("yield_col")
    if ycol and ycol in cols:
        vals = []
        for r in rows:
            try:
                vals.append(float(r[ycol]))
            except Exception:
                pass
        if vals:
            result["yield_stats"] = {
                "col": ycol,
                "n_valid": len(vals),
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "mean": round(statistics.mean(vals), 4),
                "stdev": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                "n_unique": len(set(vals)),
            }

    return result


def check_synthetic_markers(fname):
    """
    Heuristic: if last rows have very precise float values with many decimals
    in columns that earlier had integer-like values, data is likely augmented.
    """
    fpath = DATA_DIR / fname
    if not fpath.exists():
        return None
    with open(fpath, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return None
    first_vals = list(rows[0].values())
    last_vals = list(rows[-1].values())
    first_decimals = max(
        (len(v.split(".")[-1]) if "." in v else 0) for v in first_vals if v
    )
    last_decimals = max(
        (len(v.split(".")[-1]) if "." in v else 0) for v in last_vals if v
    )
    return {
        "first_row_max_decimal_places": first_decimals,
        "last_row_max_decimal_places": last_decimals,
        "likely_augmented": last_decimals > first_decimals + 5,
    }


results = {}
for fname, meta in DATASETS.items():
    print(f"Auditing: {fname}")
    r = audit_file(fname, meta)
    synth = check_synthetic_markers(fname)
    if synth:
        r["synthetic_check"] = synth
    results[fname] = r

# Final verdict table
print("\n=== VERDICT TABLE ===")
print(f"{'DATASET':<50} {'ROWS':>6} {'YIELD_COL':>12} {'VERDICT'}")
for fname, r in results.items():
    rows = r.get("n_rows", "N/A")
    ystats = r.get("yield_stats", {})
    ycol = ystats.get("col", "—")
    verdict = r.get("expected_granularity", "UNKNOWN")
    synth = r.get("synthetic_check", {})
    if synth.get("likely_augmented"):
        verdict += " + AUGMENTED"
    print(f"  {fname:<50} {str(rows):>6} {ycol:>12}  {verdict}")

with open(OUT_PATH, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nAudit saved → {OUT_PATH}")
