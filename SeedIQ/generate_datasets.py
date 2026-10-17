import os
import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# LEGACY GENERATOR — superseded by the contract datasets consumed by
# train_all_models.py. The schemas written here do NOT match the API contract:
# running this file would replace data/crop_production_karnataka.csv with a
# Rainfall/Temperature/Humidity/Soil_Type/Fertilizer/Production layout instead
# of the Crop/Season/Area_Hectares/Yield_Tonnes contract the models expect.
# Writing is therefore guarded so existing datasets are never silently lost.
# ---------------------------------------------------------------------------
os.makedirs('data', exist_ok=True)

FORCE_OVERWRITE = os.environ.get("SEEDIQ_ALLOW_DATASET_OVERWRITE", "").strip().lower() in (
    "1", "true", "yes", "on")


def write_dataset(df, path):
    """Write only when the target file is absent, or overwriting was forced."""
    if os.path.exists(path) and not FORCE_OVERWRITE:
        print(f"SKIPPED {path}: file already exists and was NOT overwritten "
              f"(set SEEDIQ_ALLOW_DATASET_OVERWRITE=1 to force).")
        return False
    df.to_csv(path, index=False)
    print(f"Generated {path} successfully with {len(df)} rows.")
    return True

crops = [
    "Rice", "Maize", "Jute", "Cotton", "Coconut", "Papaya", "Orange", "Apple",
    "Muskmelon", "Watermelon", "Grapes", "Mango", "Banana", "Pomegranate",
    "Lentil", "Blackgram", "Mungbean", "Mothbeans", "Kidneybeans", "Pigeonpeas",
    "Chickpea", "Coffee"
]

print("Generating 22-class Crop Recommendation Dataset (merged_ml_dataset.csv)...")
np.random.seed(42)
crop_data = []

# Generate 100 records per crop -> 2200 records total
for crop in crops:
    for _ in range(100):
        # Set realistic ranges per crop
        if crop == "Rice":
            n = np.random.uniform(70, 100)
            p = np.random.uniform(35, 60)
            k = np.random.uniform(30, 50)
            temp = np.random.uniform(20, 28)
            hum = np.random.uniform(75, 90)
            ph = np.random.uniform(5.5, 6.8)
            rain = np.random.uniform(180, 260)
        elif crop == "Wheat":
            n = np.random.uniform(60, 90)
            p = np.random.uniform(40, 60)
            k = np.random.uniform(30, 45)
            temp = np.random.uniform(15, 23)
            hum = np.random.uniform(50, 65)
            ph = np.random.uniform(6.0, 7.2)
            rain = np.random.uniform(60, 100)
        elif crop == "Coffee":
            n = np.random.uniform(90, 120)
            p = np.random.uniform(40, 60)
            k = np.random.uniform(30, 50)
            temp = np.random.uniform(22, 28)
            hum = np.random.uniform(50, 65)
            ph = np.random.uniform(5.5, 6.5)
            rain = np.random.uniform(120, 180)
        else:
            n = np.random.uniform(40, 100)
            p = np.random.uniform(30, 70)
            k = np.random.uniform(20, 60)
            temp = np.random.uniform(18, 32)
            hum = np.random.uniform(40, 85)
            ph = np.random.uniform(5.0, 7.8)
            rain = np.random.uniform(50, 200)
            
        crop_data.append({
            "Nitrogen": round(n, 1),
            "Phosphorus": round(p, 1),
            "Potassium": round(k, 1),
            "Temperature": round(temp, 2),
            "Humidity": round(hum, 2),
            "pH": round(ph, 2),
            "Rainfall": round(rain, 2),
            "Crop": crop
        })

df_crop = pd.DataFrame(crop_data)
write_dataset(df_crop, "data/merged_ml_dataset.csv")

print("Generating Yield Prediction Dataset (crop_production_karnataka.csv)...")
yield_data = []
seasons = ["Kharif", "Rabi", "Zaid"]
soils = ["Clayey", "Sandy", "Loamy", "Black", "Red", "Alluvial"]
fertilizers = ["Urea", "DAP", "NPK 19-19-19", "MOP", "Compost"]

for _ in range(1200):
    c = np.random.choice(crops)
    s = np.random.choice(seasons)
    area = np.random.uniform(1.0, 15.0)
    rain = np.random.uniform(50.0, 250.0)
    temp = np.random.uniform(18.0, 34.0)
    hum = np.random.uniform(40.0, 90.0)
    soil = np.random.choice(soils)
    fert = np.random.choice(fertilizers)
    
    # Simple logic for yields
    base = area * 3.5
    if c == "Coffee":
        base = area * 1.5
    elif c == "Sugarcane":
        base = area * 60.0
        
    production = base + np.random.normal(0, base * 0.1)
    production = max(production, 0.1)
    yield_val = production / area
    
    yield_data.append({
        "Crop": c,
        "Season": s,
        "Area": round(area, 2),
        "Rainfall": round(rain, 2),
        "Temperature": round(temp, 2),
        "Humidity": round(hum, 2),
        "Soil_Type": soil,
        "Fertilizer": fert,
        "Production": round(production, 2),
        "Yield": round(yield_val, 2)
    })

df_yield = pd.DataFrame(yield_data)
write_dataset(df_yield, "data/crop_production_karnataka.csv")

print("Generating Seed Viability Dataset (seed_viability_data.csv)...")
seed_data = []
colors = ["Brown", "Yellow", "Cream", "Red", "Black"]

for _ in range(600):
    moisture = np.random.uniform(8.0, 16.0)
    weight = np.random.uniform(20.0, 80.0)
    temp = np.random.uniform(10.0, 30.0)
    hum = np.random.uniform(40.0, 80.0)
    age = np.random.uniform(1.0, 18.0) # months
    bulk_density = np.random.uniform(0.5, 0.9)
    length = np.random.uniform(4.0, 10.0)
    width = np.random.uniform(2.0, 5.0)
    color = np.random.choice(colors)
    
    # Viability rule
    viable = 1 if (10.0 <= moisture <= 13.5) and (weight >= 40.0) and (age <= 12.0) else 0
    # Add noise
    if np.random.rand() < 0.05:
        viable = 1 - viable
        
    seed_data.append({
        "Moisture": round(moisture, 2),
        "Weight": round(weight, 2),
        "Storage_Temperature": round(temp, 2),
        "Storage_Humidity": round(hum, 2),
        "Seed_Age": round(age, 1),
        "Bulk_Density": round(bulk_density, 3),
        "Seed_Length": round(length, 2),
        "Seed_Width": round(width, 2),
        "Color": color,
        "Viability": viable
    })

df_seed = pd.DataFrame(seed_data)
write_dataset(df_seed, "data/seed_viability_data.csv")
