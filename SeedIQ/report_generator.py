import os
import json
import datetime
import pandas as pd
from experiment_tracker import get_db_connection

def generate_experiment_report(exp_result):
    """Generates HTML, JSON, and CSV reports for a completed experiment."""
    if not exp_result:
        return None
        
    exp_id = exp_result["exp_id"]
    task = exp_result["task"]
    best_eval = exp_result["best_eval"]
    all_evals = exp_result["all_evals"]
    ds_version = exp_result["dataset_version"]
    exp_status = exp_result.get("exp_status", "COMPLETED")
    env_metadata = exp_result.get("env_metadata", {})
    
    report_dir = os.path.join("reports", exp_id)
    os.makedirs(report_dir, exist_ok=True)
    
    html_path = os.path.join(report_dir, "report.html")
    metrics_json_path = os.path.join(report_dir, "metrics.json")
    hyperparams_json_path = os.path.join(report_dir, "hyperparameters.json")
    test_results_json_path = os.path.join(report_dir, "test_results.json")
    csv_path = os.path.join(report_dir, "model_comparison.csv")
    
    # 1. Save metrics.json
    metrics_data = {
        "experiment_id": exp_id,
        "task": task,
        "status": exp_status,
        "best_model": best_eval["model_name"],
        "metrics": best_eval["metrics"],
        "training_time": best_eval["train_time"],
        "inference_time": best_eval["inf_time"],
        "env_metadata": env_metadata
    }
    with open(metrics_json_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_data, f, indent=4)
        
    # 2. Save hyperparameters.json
    hyperparams_data = {
        "experiment_id": exp_id,
        "best_model": best_eval["model_name"],
        "best_parameters": best_eval["best_params"],
        "all_model_parameters": {ev["model_name"]: ev["best_params"] for ev in all_evals}
    }
    with open(hyperparams_json_path, 'w', encoding='utf-8') as f:
        json.dump(hyperparams_data, f, indent=4)
        
    # 3. Save test_results.json
    test_results_data = {
        "experiment_id": exp_id,
        "dataset_version": ds_version,
        "best_model": best_eval["model_name"],
        "test_score": best_eval["test_score"],
        "train_score": best_eval["train_score"],
        "generalization_gap": best_eval["gen_gap"],
        "overfitting_status": best_eval["overfit_status"],
        "all_evaluations": [
            {
                "model": ev["model_name"],
                "cv_score": ev["cv_score"],
                "test_score": ev["test_score"],
                "train_score": ev["train_score"],
                "gen_gap": ev["gen_gap"],
                "overfit_status": ev["overfit_status"]
            } for ev in all_evals
        ]
    }
    with open(test_results_json_path, 'w', encoding='utf-8') as f:
        json.dump(test_results_data, f, indent=4)

    # 4. Save CSV Model Comparison
    rows = []
    for ev in all_evals:
        r = {
            "Model": ev["model_name"],
            "CV_Score": f"{ev['cv_score']:.4f}",
            "Test_Score": f"{ev['test_score']:.4f}",
            "Train_Score": f"{ev['train_score']:.4f}",
            "Generalization_Gap": f"{ev['gen_gap']:.4f}",
            "Overfitting_Status": ev["overfit_status"],
            "Train_Time_s": f"{ev['train_time']:.2f}"
        }
        rows.append(r)
    df_comp = pd.DataFrame(rows)
    df_comp.to_csv(csv_path, index=False)
    
    # 5. Save HTML Report
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>SeedIQ Experiment Report - {exp_id}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background-color: #0d1012; color: #e2e8f0; margin: 0; padding: 40px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 24px; margin-bottom: 24px; border: 1px solid #334155; }}
        h1 {{ color: #10b981; font-size: 28px; margin-bottom: 8px; }}
        h2 {{ color: #38bdf8; font-size: 20px; border-bottom: 1px solid #334155; padding-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ border: 1px solid #334155; padding: 12px; text-align: left; }}
        th {{ background-color: #0f172a; color: #10b981; }}
        .highlight {{ color: #f59e0b; font-weight: bold; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; background: #065f46; color: #34d399; font-weight: 600; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>🌱 SeedIQ Model Evaluation Report</h1>
        <p><strong>Experiment ID:</strong> {exp_id} | <strong>Task:</strong> {task} | <strong>Dataset Version:</strong> {ds_version}</p>
        <p><span class="badge">STATUS: {exp_status}</span></p>
    </div>

    <div class="card">
        <h2>Executive Summary</h2>
        <p><strong>Selected Best Model:</strong> <span class="highlight">{best_eval['model_name']}</span></p>
        <p><strong>Test Performance Score:</strong> {best_eval['test_score']:.4f}</p>
        <p><strong>Overfitting Status:</strong> {best_eval['overfit_status']} (Generalization Gap: {best_eval['gen_gap']:.4f})</p>
        <p><strong>Best Hyperparameters:</strong> <code>{json.dumps(best_eval['best_params'])}</code></p>
    </div>

    <div class="card">
        <h2>Model Comparison Matrix</h2>
        {df_comp.to_html(classes="table", index=False)}
    </div>
</body>
</html>
"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    # Register report in SQLite
    with get_db_connection() as conn:
        cursor = conn.cursor()
        report_id = f"REP-{exp_id}"
        cursor.execute('''
            INSERT OR REPLACE INTO reports (report_id, experiment_id, report_type, file_path, summary_json)
            VALUES (?, ?, 'HTML', ?, ?)
        ''', (report_id, exp_id, html_path, json.dumps(metrics_data)))
        conn.commit()

    print(f"📊 Generated report artifacts in {report_dir}")
    return html_path
