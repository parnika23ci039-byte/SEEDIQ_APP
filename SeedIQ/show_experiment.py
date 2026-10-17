import sys
import json
from experiment_tracker import get_db_connection

def show_experiment(exp_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM experiments WHERE experiment_id = ?", (exp_id,))
        exp = cursor.fetchone()
        
        if not exp:
            print(f"❌ Experiment ID '{exp_id}' not found in seediq.db")
            return
            
        print("\n" + "="*50)
        print(f"SEEDIQ EXPERIMENT DETAILS: {exp['experiment_id']}")
        print("="*50)
        print(f"Task:            {exp['task_name']}")
        print(f"Dataset Name:    {exp['dataset_name']}")
        print(f"Dataset Version: {exp['dataset_version']}")
        print(f"Best Model:      {exp['model_name']}")
        print(f"Status:          {exp['status']}")
        if exp['error_message']:
            print(f"Error Message:   {exp['error_message']}")
        print(f"Training Time:   {exp['training_time']}s" if exp['training_time'] is not None else "Training Time:   N/A")
        print(f"Inference Time:  {exp['inference_time']}s" if exp['inference_time'] is not None else "Inference Time:  N/A")
        print(f"Model Path:      {exp['model_path']}")
        
        # Trials
        cursor.execute("SELECT COUNT(*) as t_count FROM hyperparameter_trials WHERE experiment_id = ?", (exp_id,))
        t_row = cursor.fetchone()
        if t_row:
            print(f"Recorded Trials: {t_row['t_count']}")

        # Metrics
        cursor.execute("SELECT metric_name, metric_value FROM experiment_metrics WHERE experiment_id = ?", (exp_id,))
        metrics = cursor.fetchall()
        if metrics:
            print("\nTest Metrics:")
            for m in metrics:
                print(f"  * {m['metric_name']}: {m['metric_value']:.4f}")
            
        # Model Version
        cursor.execute("SELECT version, best_parameters_json FROM model_versions WHERE experiment_id = ?", (exp_id,))
        mv = cursor.fetchone()
        if mv:
            print(f"\nModel Version:   {mv['version']}")
            print(f"Best Params:     {mv['best_parameters_json']}")
            
        # Report
        cursor.execute("SELECT file_path FROM reports WHERE experiment_id = ?", (exp_id,))
        rep = cursor.fetchone()
        if rep:
            print(f"Report Path:     {rep['file_path']}")
            
        print("="*50)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python show_experiment.py <experiment_id>")
    else:
        show_experiment(sys.argv[1])
