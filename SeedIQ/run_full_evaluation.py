import os
import sys
import time
import json
from experiment_tuner import run_experiment_pipeline
from report_generator import generate_experiment_report
from run_tests import run_test_suite
from dataset_auditor import run_dataset_audit

def run_full_evaluation():
    start_time = time.time()
    
    # 1. Run Dataset Audit
    run_dataset_audit()
    
    # 2. Run Automated Unit & Integration Tests
    run_test_suite(full=True)
    
    # 3. Run All Experiments & Tuning
    experiments = [
        ("Crop_Recommendation", "data/merged_ml_dataset.csv", "Crop", True),
        ("Yield_Prediction", "data/crop_production_karnataka.csv", "Yield_Tonnes", False),
        ("Seed_Viability", "data/seed_viability_data.csv", "Viable", True)
    ]
    
    completed_runs = []
    for task_name, path, target, is_class in experiments:
        res = run_experiment_pipeline(task_name, path, target, is_class)
        if res:
            report_path = generate_experiment_report(res)
            completed_runs.append((res, report_path))

    duration = time.time() - start_time
    
    # Print Terminal Summary
    print("\n" + "="*50)
    print("SEEDIQ MODEL EVALUATION SUMMARY")
    print("="*50)
    
    for res, r_path in completed_runs:
        best_eval = res['best_eval']
        b_score = res.get('baseline_score', 0.0)
        imprv = best_eval['test_score'] - b_score
        print(f"\nTask:                {res['task']}")
        print(f"Experiment ID:       {res['exp_id']}")
        print(f"Dataset Version:     {res['dataset_version']}")
        print(f"Baseline Score:      {b_score:.4f}")
        print(f"Best Model:          {best_eval['model_name']} (Test Score: {best_eval['test_score']:.4f})")
        print(f"Baseline Improvement:{imprv:+.4f}")
        print(f"Best Hyperparameters:{json.dumps(best_eval['best_params'])}")
        print(f"CV Score:            {best_eval['cv_score']:.4f}")
        print(f"Generalization Gap:  {best_eval['gen_gap']:.4f} ({best_eval['overfit_status']})")
        if best_eval.get('warnings'):
            print(f"Warnings:            {', '.join(best_eval['warnings'])}")
        print(f"Training Time:       {best_eval['train_time']:.2f}s")
        print(f"Inference Time:      {best_eval['inf_time']:.4f}s")
        print(f"Report:              {r_path}")
        print("-" * 50)

    print(f"\nTotal Pipeline Duration: {duration:.2f}s")
    print("Database Updated:    seediq.db")
    print("Dataset Audit:       reports/dataset_audit/dataset_audit.html")
    print("="*50)

if __name__ == "__main__":
    run_full_evaluation()
