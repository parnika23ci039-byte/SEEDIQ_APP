import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
import os

# Create dummy datasets for demonstration
os.makedirs('data', exist_ok=True)

# Guard: the filenames below are the SAME canonical datasets used by
# train_all_models.py (and by the API). This dummy-data notebook must never
# silently replace real training data, so writes are opt-in.
FORCE_OVERWRITE = os.environ.get('SEEDIQ_ALLOW_DATASET_OVERWRITE', '').strip().lower() in (
    '1', 'true', 'yes', 'on')


def write_dataset(df, path):
    if os.path.exists(path) and not FORCE_OVERWRITE:
        print(f"SKIPPED {path}: file already exists and was NOT overwritten "
              f"(set SEEDIQ_ALLOW_DATASET_OVERWRITE=1 to force).")
        return False
    df.to_csv(path, index=False)
    print(f"Generated {path} successfully with {len(df)} rows.")
    return True


print("Generating dummy datasets for SeedIQ (existing files are preserved)...")

# 1. merged_ml_dataset.csv (General crop & soil data)
df_merged = pd.DataFrame({
    'Nitrogen': np.random.randint(50, 150, 100),
    'Phosphorus': np.random.randint(20, 80, 100),
    'Potassium': np.random.randint(20, 80, 100),
    'Temperature': np.random.uniform(15, 35, 100),
    'Humidity': np.random.uniform(40, 90, 100),
    'pH': np.random.uniform(5.5, 7.5, 100),
    'Rainfall': np.random.uniform(50, 300, 100),
    'Crop': np.random.choice(['Rice', 'Wheat', 'Maize', 'Sugarcane', 'Cotton'], 100)
})
write_dataset(df_merged, 'data/merged_ml_dataset.csv')

# 2. crop_production_karnataka.csv
df_yield = pd.DataFrame({
    'Crop': np.random.choice(['Rice', 'Wheat', 'Maize'], 100),
    'Season': np.random.choice(['Kharif', 'Rabi', 'Zaid'], 100),
    'Area_Hectares': np.random.uniform(1, 10, 100),
    'Yield_Tonnes': np.random.uniform(2, 20, 100)
})
write_dataset(df_yield, 'data/crop_production_karnataka.csv')

# 3. seed_viability_data.csv
df_seed = pd.DataFrame({
    'Moisture_Level': np.random.uniform(8, 15, 100),
    'Weight_g': np.random.uniform(30, 70, 100),
    'Viable': np.random.choice([0, 1], 100)
})
write_dataset(df_seed, 'data/seed_viability_data.csv')

print("Dummy data step complete.")

# --- Preprocessing Pipeline ---

def preprocess_crop_data():
    df = pd.read_csv('data/merged_ml_dataset.csv')
    # Handle missing values
    df.fillna(df.mean(numeric_only=True), inplace=True)
    
    # Feature Scaling
    scaler = StandardScaler()
    X = df.drop('Crop', axis=1)
    X_scaled = scaler.fit_transform(X)
    
    # Encoding
    le = LabelEncoder()
    y = le.fit_transform(df['Crop'])
    
    return train_test_split(X_scaled, y, test_size=0.2, random_state=42)

print("Preprocessing complete. Data ready for training.")
