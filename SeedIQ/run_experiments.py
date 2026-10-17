import os
import sys
from experiment_tuner import run_experiment_pipeline
from report_generator import generate_experiment_report

def main():
    print("\n==================================================")
    print("🚀 RUNNING SEEDIQ ML EXPERIMENTS & HYPERPARAMETER TUNING")
    print("==================================================")
    
    experiments = [
        ("Crop_Recommendation", "data/merged_ml_dataset.csv", "Crop", True),
        ("Yield_Prediction", "data/crop_production_karnataka.csv", "Yield_Tonnes", False),
        ("Seed_Viability", "data/seed_viability_data.csv", "Viable", True)
    ]
    
    results = []
    for task_name, path, target, is_class in experiments:
        res = run_experiment_pipeline(task_name, path, target, is_class)
        if res:
            report_path = generate_experiment_report(res)
            results.append((res, report_path))
            
    print("\n==================================================")
    print("✅ ALL EXPERIMENTS COMPLETED SUCCESSFULLY!")
    for res, r_path in results:
        print(f" Task: {res['task']} | Best Model: {res['best_eval']['model_name']} | Report: {r_path}")
    print("==================================================")

if __name__ == "__main__":
    main()
