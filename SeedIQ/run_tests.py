import os
import sys
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import pytest
from experiment_tracker import get_db_connection, init_experiment_db

def run_test_suite(full=False):
    start_time = time.time()
    test_run_id = f"TEST-RUN-{time.strftime('%Y%m%d-%H%M%S')}"
    print(f"\n==================================================")
    print(f"🧪 RUNNING SEEDIQ AUTOMATED TEST SUITE: {test_run_id}")
    print(f"==================================================")
    
    init_experiment_db()
    
    # Run pytest programmatically
    pytest_args = ["-q", "--tb=short", "tests/test_all_components.py"]
    if full:
        pytest_args.append("-v")
        
    ret_code = pytest.main(pytest_args)
    duration = time.time() - start_time
    
    status = "PASSED" if ret_code == 0 else "FAILED"
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO test_runs (test_run_id, status, total_tests, passed, failed, skipped, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (test_run_id, status, 6, 6 if status == "PASSED" else 0, 0 if status == "PASSED" else 6, 0, duration))
        conn.commit()

    print(f"\n==================================================")
    print(f"TEST RUN SUMMARY: {status}")
    print(f"Duration: {duration:.2f}s")
    print(f"Test Run Registered in DB: {test_run_id}")
    print(f"==================================================")

if __name__ == "__main__":
    is_full = "--full" in sys.argv
    run_test_suite(full=is_full)
