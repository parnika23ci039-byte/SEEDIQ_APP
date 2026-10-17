import sqlite3
from experiment_tracker import get_db_connection

def list_experiments():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT e.experiment_id, e.timestamp, e.task_name, e.status, e.model_name,
                   (SELECT metric_value FROM experiment_metrics m WHERE m.experiment_id = e.experiment_id ORDER BY m.id DESC LIMIT 1) as score
            FROM experiments e
            ORDER BY e.id DESC
        ''')
        rows = cursor.fetchall()
        
        print("\n==================================================")
        print("SEEDIQ EXPERIMENT HISTORY")
        print("==================================================")
        if not rows:
            print("No experiments found in database.")
            print("==================================================")
            return

        print(f"{'Experiment ID':<45} | {'Date':<10} | {'Task':<20} | {'Status':<10} | {'Best Model':<15} | {'Score'}")
        print("-" * 120)
        for r in rows:
            exp_id = r['experiment_id']
            date_str = str(r['timestamp'])[:10] if r['timestamp'] else 'N/A'
            task = r['task_name'] or 'N/A'
            status = r['status'] or 'UNKNOWN'
            model = r['model_name'] or 'N/A'
            score_str = f"{r['score']:.4f}" if r['score'] is not None else "N/A"
            print(f"{exp_id:<45} | {date_str:<10} | {task:<20} | {status:<10} | {model:<15} | {score_str}")
        print("==================================================")

if __name__ == "__main__":
    list_experiments()
