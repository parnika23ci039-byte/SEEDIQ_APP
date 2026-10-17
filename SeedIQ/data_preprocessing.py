import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder, StandardScaler

def detect_dataset_type(df):
    """Detects the type of agricultural dataset based on columns."""
    columns = [col.lower() for col in df.columns]
    
    # Check for Crop Recommendation
    crop_keywords = {'nitrogen', 'phosphorus', 'potassium', 'rainfall', 'ph'}
    if any(k in columns for k in crop_keywords) or ('crop' in columns and ('nitrogen' in columns or 'n' in columns)):
        return 'crop'
        
    # Check for Seed Viability
    seed_keywords = {'moisture', 'moisture_level', 'viable', 'viability', 'weight_g'}
    if any(k in columns for k in seed_keywords) and 'viable' in columns:
        return 'seed'
        
    # Check for Yield Prediction. `crop` alone must not classify a table as a
    # crop-recommendation table (the yield table has a Crop column too), so the
    # crop check above requires soil/weather columns and the yield check below
    # accepts any table carrying area + yield/tonnes columns.
    yield_keywords = {'yield', 'yield_tonnes', 'area', 'area_hectares', 'tonnes'}
    if any(k in columns for k in yield_keywords) or 'yield' in columns:
        return 'yield'
        
    return 'unknown'

def discover_and_route_datasets(data_dir='data'):
    """Scans data directory for CSV files and classifies them.

    The canonical dataset of each domain is picked first. The directory scan is
    only a fallback and runs in sorted order, because `os.listdir` order is
    arbitrary and used to route a domain at the first file that happened to
    match — which trained models on the wrong table.
    """
    discovered = {'crop': None, 'yield': None, 'seed': None}
    
    if not os.path.exists(data_dir):
        return discovered

    canonical = {
        'crop': 'Crop_recommendation.csv',
        # The ACTIVE yield table is the one derived from the real ICRISAT source.
        # The legacy synthetic generator output is a last-resort fallback only.
        'yield': 'yield_icrisat_karnataka.csv',
        'seed': 'seed_viability_data.csv',
    }
    for domain, filename in canonical.items():
        path = os.path.join(data_dir, filename)
        if os.path.exists(path):
            discovered[domain] = path

    # Fallbacks are tried only for domains the canonical names did not route.
    fallbacks = {'yield': 'crop_production_karnataka.csv'}
    for domain, filename in fallbacks.items():
        path = os.path.join(data_dir, filename)
        if discovered[domain] is None and os.path.exists(path):
            discovered[domain] = path
        
    # Fallback scan for any domain still unrouted.
    for file in sorted(os.listdir(data_dir)):
        if not file.endswith('.csv'):
            continue
        path = os.path.join(data_dir, file)
        try:
            # Read first few rows to inspect columns
            df = pd.read_csv(path, nrows=5)
            dtype = detect_dataset_type(df)
            if dtype in discovered and discovered[dtype] is None:
                discovered[dtype] = path
        except Exception as e:
            print(f"Error inspecting file {file}: {e}")
                
    return discovered

def preprocess_crop_data(path):
    """Preprocesses crop dataset, returning scaled features, labels, and preprocessors."""
    df = pd.read_csv(path).dropna()
    
    # Rename columns if needed (e.g. for N, P, K, label, crops -> Nitrogen, Phosphorus, Potassium, Crop)
    rename_dict = {
        'n': 'Nitrogen', 'p': 'Phosphorus', 'k': 'Potassium',
        'temperature': 'Temperature', 'humidity': 'Humidity', 'ph': 'pH', 'rainfall': 'Rainfall',
        'label': 'Crop', 'crops': 'Crop'
    }
    df = df.rename(columns={col: rename_dict[col.lower()] for col in df.columns if col.lower() in rename_dict})
    
    # Select numeric features
    feature_cols = ['Nitrogen', 'Phosphorus', 'Potassium', 'Temperature', 'Humidity', 'pH', 'Rainfall']
    # Fallback to whatever numeric columns exist if standard names aren't present
    if not all(col in df.columns for col in feature_cols):
        X = df.drop('Crop', axis=1, errors='ignore').select_dtypes(include=np.number)
    else:
        X = df[feature_cols]
        
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    crop_encoder = LabelEncoder()
    if 'Crop' in df.columns:
        y = crop_encoder.fit_transform(df['Crop'])
    else:
        y = crop_encoder.fit_transform(pd.Series(['unknown'] * len(df)))
    
    return X_scaled, y, scaler, crop_encoder

def preprocess_yield_data(path):
    """Preprocesses yield dataset, returning scaled features, labels, and preprocessors."""
    df = pd.read_csv(path).dropna()
    
    # Ensure categorical columns exist and encode them
    crop_encoder = LabelEncoder()
    season_encoder = LabelEncoder()
    
    df_encoded = df.copy()
    if 'Crop' in df_encoded.columns:
        df_encoded['Crop'] = crop_encoder.fit_transform(df_encoded['Crop'])
    else:
        df_encoded['Crop'] = 0
        
    if 'Season' in df_encoded.columns:
        df_encoded['Season'] = season_encoder.fit_transform(df_encoded['Season'])
    else:
        df_encoded['Season'] = 0
        
    # Fallback if names are slightly different
    for col in ['Area', 'area']:
        if col in df.columns and 'Area_Hectares' not in df.columns:
            df_encoded['Area_Hectares'] = df_encoded[col]
            
    df_encoded['Area_Sq'] = df_encoded['Area_Hectares'] ** 2
    df_encoded['Crop_Season'] = df_encoded['Crop'] * df_encoded['Season']
    
    feature_cols = ['Crop', 'Season', 'Area_Hectares', 'Area_Sq', 'Crop_Season']
    X = df_encoded[feature_cols]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    y = df_encoded['Yield_Tonnes'] if 'Yield_Tonnes' in df_encoded.columns else df_encoded.iloc[:, -1]
    
    return X_scaled, y, scaler, crop_encoder, season_encoder

def preprocess_seed_data(path):
    """Preprocesses seed dataset, returning scaled features, labels, and preprocessor."""
    df = pd.read_csv(path).dropna()

    # The seed-viability API accepts exactly these two measurements. Falling back
    # to "every other numeric column" silently trained models on a different
    # schema (a 7-column seed-variety dataset), which is how the deployed route
    # ended up with artifacts it could never use. Refuse instead of guessing.
    feature_cols = ['Moisture_Level', 'Weight_g']
    missing = [col for col in feature_cols if col not in df.columns]
    if missing:
        raise ValueError(
            f"Seed dataset {path!r} is missing {missing} (found {list(df.columns)}). "
            "Refusing to train on a schema the seed-viability API does not accept."
        )
    X = df[feature_cols]
        
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    y = df['Viable'] if 'Viable' in df.columns else np.zeros(len(df))
    
    return X_scaled, y, scaler

