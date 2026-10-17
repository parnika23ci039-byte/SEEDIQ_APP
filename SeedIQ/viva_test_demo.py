import os
import json
import sqlite3

def run_diagnostics():
    print("=" * 60)
    print("🌱 SeedIQ - Viva Demonstration & Diagnostics Script")
    print("=" * 60)

    # 1. Verify Knowledge Bases
    print("\n[1/4] Verifying reorganized Knowledge Bases...")
    kb_dir = "knowledge_base"
    kb_files = [
        "growth_planner.json", "crop_disease.json", "soil_health.json",
        "market_analysis.json", "storage_db.json", "preservation_steps.json"
    ]
    
    if not os.path.exists(kb_dir):
        print(f"❌ Error: Directory '{kb_dir}' not found!")
        return
        
    for file in kb_files:
        path = os.path.join(kb_dir, file)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"  -> ✅ {file} loaded successfully ({len(data)} entries)")
            except Exception as e:
                print(f"  -> ❌ {file} has JSON formatting errors: {e}")
        else:
            print(f"  -> ❌ {file} is MISSING from '{kb_dir}'!")

    # 2. Database Checks
    print("\n[2/4] Verifying SQLite database and tables...")
    db_path = "seediq.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check Users table
            users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            print(f"  -> ✅ Database connected successfully. Found {users} registered users.")
            
            # Check Admin accounts
            admins = cursor.execute("SELECT username, role FROM users WHERE LOWER(role) = 'admin'").fetchall()
            if admins:
                print("  -> ✅ Admin accounts discovered:")
                for admin in admins:
                    print(f"     - {admin[0]} (Role: {admin[1]})")
            else:
                print("  -> ⚠️ No Admin accounts found. Register an Admin using the signup page.")
            
            # Check Predictions table
            preds = cursor.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            print(f"  -> ✅ Predictions table contains {preds} records.")
            
            conn.close()
        except Exception as e:
            print(f"  -> ❌ Database diagnostics failed: {e}")
    else:
        print("  -> ⚠️ seediq.db not created yet. It will initialize when starting the app.")

    # 3. Model Preprocessor Check
    print("\n[3/4] Checking trained models and preprocessor scalars...")
    models_dir = "models"
    model_files = [
        "rf_model.pkl", "xgb_model.pkl", "svm_model.pkl", "meta_model.pkl",
        "crop_scaler.pkl", "yield_scaler.pkl", "seed_scaler.pkl",
        "crop_encoder.pkl", "yield_crop_encoder.pkl", "yield_season_encoder.pkl"
    ]
    
    missing_models = False
    for file in model_files:
        path = os.path.join(models_dir, file)
        if os.path.exists(path):
            print(f"  -> ✅ Model file '{file}' found.")
        else:
            print(f"  -> ❌ Model file '{file}' is MISSING in '{models_dir}/'!")
            missing_models = True
            
    if missing_models:
        print("\n  👉 Action Required: Please run 'python train_all_models.py' to generate missing models.")
    else:
        print("\n  👉 Status: All model binaries are present and ready.")

    # 4. viva Demonstration Script
    print("\n[4/4] VIVA PRESENTATION STEPS & ROADMAP:")
    print("-" * 50)
    print("Step 1: Run 'python generate_datasets.py' to populate 22-class CSV datasets.")
    print("Step 2: Run 'python train_all_models.py' to fit classical, quantum, and stacking meta-models.")
    print("Step 3: Run 'python app.py' to start the local Flask server on http://127.0.0.1:5000.")
    print("Step 4: Register a 'Farmer' account, log in, run a Crop AI recommendation,")
    print("        and showcase the new Soil Diagnostic, Disease Advisory, and Growth timeline.")
    print("Step 5: Run a Yield AI prediction, showcase the Profit Calculator, and Storage recommendations.")
    print("Step 6: Log out, register an 'Admin' account, and showcase the secure `/admin` console.")
    print("=" * 60)

if __name__ == "__main__":
    run_diagnostics()
