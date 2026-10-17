"""
Sync and preprocess all SeedIQ datasets to Supabase.
This script scans SeedIQ/data for primary CSV datasets,
validates and preprocessed each with O(1) streaming/chunking memory (<100MB RAM),
uploads both raw and preprocessed versions to Supabase Storage bucket 'seediq-datasets',
and inserts catalog records into Supabase 'datasets' and 'dataset_versions' tables.
"""

import os
import sys
import glob

# Ensure SeedIQ directory is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from dataset_service import process_and_store_dataset
from supabase_client import supabase

def sync_all_datasets():
    data_dir = os.path.join(SCRIPT_DIR, 'data')
    if not os.path.exists(data_dir):
        print(f"[!] Data directory not found at {data_dir}")
        return

    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    print(f"[*] Found {len(csv_files)} CSV files in {data_dir}")

    # Exclude temporary processed files and unit test files from previous test runs
    primary_datasets = []
    for p in csv_files:
        name = os.path.basename(p)
        if "_processed.csv" in name:
            continue
        if name.startswith("2026") and ("unit_test" in name or "processed" in name):
            continue
        primary_datasets.append(p)

    print(f"[*] Syncing {len(primary_datasets)} primary datasets to Supabase and database...")

    success_count = 0
    skipped_count = 0
    error_count = 0

    for idx, filepath in enumerate(primary_datasets, 1):
        filename = os.path.basename(filepath)
        filesize_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"\n[{idx}/{len(primary_datasets)}] Processing '{filename}' ({filesize_mb:.2f} MB)...")

        try:
            res = process_and_store_dataset(
                file_input=filepath,
                filename=filename,
                user_id="system_admin",
                user_role="Admin"
            )

            if res.get("status") == "success":
                success_count += 1
                print(f"  -> SUCCESS! Type: {res.get('detected_type')} | Rows: {res.get('rows')} | Cols: {res.get('columns')} | Version: {res.get('version')}")
                if res.get("original_storage_path"):
                    print(f"  -> Supabase Original: {res.get('original_storage_path')}")
                if res.get("processed_storage_path"):
                    print(f"  -> Supabase Processed: {res.get('processed_storage_path')}")
            else:
                error_count += 1
                print(f"  -> ERROR: {res.get('message')}")

        except Exception as e:
            error_count += 1
            print(f"  -> EXCEPTION: {str(e)}")

    print("\n" + "="*50)
    print(f"Sync complete! Total: {len(primary_datasets)} | Success: {success_count} | Errors: {error_count}")
    print("="*50)

if __name__ == "__main__":
    sync_all_datasets()
