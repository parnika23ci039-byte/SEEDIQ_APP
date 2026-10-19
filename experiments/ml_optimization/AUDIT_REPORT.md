# SeedIQ ML Optimization - Audit Report

**Date**: October 9, 2026
**Status**: FUNDAMENTAL DATA MISMATCH IDENTIFIED

---

## New Evidence Obtained

### 1. Application Input/Output Audit
**Method**: Inspected `app.py` lines 2621-2650, 686-705

**Findings**:
- **App input for yield**: `crop` (string) + `area_hectares` (float)
- **App output**: `tonnes per hectare` (user-facing figure)
- **App features**: Only `Area_Hectares` + `Crop` (one-hot encoded)
- **Season**: Deprecated and ignored (not a model input)

### 2. Training Data Investigation
**Method**: Inspected `yield_icrisat_karnataka.csv`

**Findings**:
- **Columns**: Crop, District, Year, Area_Hectares, Yield_Tonnes
- **Area_Hectares meaning**: TOTAL area of crop planted in ENTIRE DISTRICT for that year
  - Example: Bangalore district planted 29,400 hectares of Rice in 2000
  - Median: 9,100 hectares (district-level aggregate)
- **Yield_Tonnes meaning**: TOTAL yield for entire district for that crop/year
  - Example: 76,000 tonnes for Bangalore Rice 2000
- **District and Year**: Used for GROUPED splitting only, NOT as prediction features

### 3. Fundamental Mismatch Discovered
**Problem**: The model is trained on district-level aggregates but used for field-level predictions

**Training context**:
- Input: District-level Area_Hectares (e.g., 29,400 ha for entire district)
- Output: District-level Yield_Tonnes (e.g., 76,000 t for entire district)
- Context: Many farmers, various soil types, different management practices

**Inference context**:
- Input: User's field size (e.g., 2.5 hectares)
- Output: Yield for that specific field
- Context: Single farmer, specific soil, specific management

**Scale mismatch**: 1000x or more (median 9,100 ha vs typical 1-10 ha user input)

### 4. Model Behavior Analysis
**Method**: Tested model predictions for different areas of the same crop

**Findings**:
- **Per-hectare predictions are nearly constant across different areas**
- Prediction std: 0.0860 t/ha across areas from 1 to 1000 hectares
- **The model acts like a lookup table for crop-specific average yield per hectare**
- **Area_Hectares feature has almost no predictive power**

**Example for Rice**:
- 1.0 ha → 2.801 t/ha
- 5.0 ha → 2.801 t/ha
- 10.0 ha → 2.801 t/ha
- 50.0 ha → 2.623 t/ha
- 100.0 ha → 2.645 t/ha
- 1000.0 ha → 2.620 t/ha

**Training data average for Rice**: 2.482 t/ha

### 5. Empirical Upper Bound Calculation
**Method**: Calculated actual maximum joint success from 440 test rows

**Results**:
- Crop accuracy: 99.55% (438/440)
- Yield ±25% accuracy: 54.55% (240/440)
- Seed accuracy: 90.00% (396/440)

**Empirical upper bound with perfect yield**:
- Joint success: **89.55%** (394/440)
- **Still below 90% by 0.45 percentage points**

**Empirical upper bound with perfect yield AND perfect seed**:
- Joint success: **99.55%** (438/440)
- **Would achieve 90%**

**Required yield accuracy for 90%**:
- Required: **100.46%** (exceeds 100% - IMPOSSIBLE)

### 6. External Data Acquisition Attempts
**Attempt 1**: Karnataka Grama Panchayat data from data.gov.in
- URL: https://data.gov.in/catalog/grama-panchayat-level-average-yield-data-summer-season-2016-17
- Download: Failed (API returned HTML instead of CSV)
- Status: Access blocker - API requires authentication or manual download

**Attempt 2**: Kaggle India Agriculture datasets
- URL: https://www.kaggle.com/datasets/pyatakov/india-agriculture-crop-production
- Download: Failed (not accessible via curl)
- Status: Access blocker - requires Kaggle account

### 7. Existing Dataset Investigation
**Dataset**: `Crop Yiled with Soil and Weather.csv` (2,597 rows)

**Findings**:
- **Columns**: Fertilizer, temp, N, P, K, yeild
- **Missing**: Crop label (critical for crop-specific predictions)
- **Features**: Has Fertilizer, N, P, K, temp (app does not collect these)
- **Correlations**: Very high (0.76-0.89), suggests synthetic data
- **Distribution**: Uniform, no outliers (suggests synthetic)
- **Compatibility**: Cannot be used without changing app input contract

**Conclusion**: Not suitable for use without major app changes.

---

## Fundamental Issue

**The yield model is invalid for the app's use case.**

1. **Data level mismatch**: Trained on district aggregates, used for field predictions
2. **Feature mismatch**: Area_Hectares means different things in training vs inference
3. **Scale mismatch**: 1000x difference between training data and app inputs
4. **Missing features**: No soil, weather, irrigation, or management data
5. **Model behavior**: Acts as a lookup table, not a genuine predictor

**The model cannot predict field-level yield because it was never trained on field-level data.**

---

## Materially Different Implementation

**None performed.**

**Reason**: All available datasets in the repository are either:
1. District-level aggregates (ICRISAT) - unsuitable for field-level prediction
2. Synthetic (seed viability, Crop Yiled with Soil and Weather) - not real measurements
3. Missing critical features (no crop labels, no app-compatible features)

**External data acquisition failed** due to API access blockers requiring manual intervention.

---

## Measured Test Result

**Best joint success**: 50.68% (223/440)
- Same as previous experiments
- No improvement possible with current data
- Mathematical ceiling: 89.55% (even with perfect yield)

---

## Access Blockers

1. **data.gov.in API**: Returns HTML instead of CSV, requires authentication or manual download
2. **Kaggle datasets**: Requires account authentication, not accessible via automated curl
3. **ICAR KRISHI portal**: Requires manual navigation, no direct download links

---

## Exact Missing Inputs/Data

To achieve 90% joint success, the following is required:

### 1. Field-Level Yield Data
- **What**: Individual field measurements with precise area and yield
- **Scale**: 10,000+ rows
- **Coverage**: All 19 Karnataka districts
- **Features**: Crop, area, soil type, fertilizer, irrigation, weather
- **Unit**: Same as app input (field-level hectares, not district aggregates)
- **Source**: Karnataka Agriculture Department field surveys
- **Status**: Not available in repository, API access blocked

### 2. Real Seed Viability Data
- **What**: Measured germination percentage from seed testing
- **Scale**: 1,000+ measurements
- **Features**: Moisture, weight, storage conditions, duration, crop variety
- **Current**: 100 synthetic rows (generated from logistic relation)
- **Source**: Agricultural research stations or seed testing laboratories
- **Status**: Not available in repository

### 3. App Input Feature Expansion
- **What**: Collect soil, weather, irrigation, fertilizer inputs from users
- **Reason**: Current app only collects crop + area (insufficient for prediction)
- **Impact**: Requires Android app changes and data collection infrastructure
- **Status**: Not implemented

---

## Conclusion

**90% joint success is not achievable with the current data and app design.**

The fundamental issue is that the yield model is trained on district-level aggregates but used for field-level predictions. This is a data mismatch that cannot be solved with model tuning or feature engineering.

**Required path forward**:
1. Acquire field-level yield data (manual download from data.gov.in required)
2. Replace synthetic seed data with real measurements
3. Expand app to collect soil, weather, irrigation inputs
4. Retrain models on field-level data with appropriate features

**Without these changes, the mathematical ceiling is 89.55% joint success.**

---

**Report prepared by**: ML Optimization Agent
**Date**: October 9, 2026
**Status**: FUNDAMENTAL DATA MISMATCH - NO NEW DATA OBTAINED
