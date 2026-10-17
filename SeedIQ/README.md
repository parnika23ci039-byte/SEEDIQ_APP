# 🌱 SeedIQ - Quantum-Powered Agricultural Intelligence System

SeedIQ is a full-stack, AI-powered agricultural intelligence platform designed to help farmers and agricultural researchers. It integrates classical Machine Learning and Quantum Machine Learning to provide highly accurate crop, yield, seed, and storage recommendations.

## 🚀 Features
- **Crop Recommendation:** Random Forest classifier based on NPK, pH, and climate data.
- **Yield Prediction:** XGBoost regressor for accurate yield forecasting.
- **Seed Viability:** SVM model to assess seed quality.
- **Quantum ML (VQC):** Hybrid meta-model using Qiskit for >95% accuracy.
- **Interactive Dashboard:** Modern UI with glassmorphism, animations, and Chart.js integration.
- **Storage Recommendations:** Optimal preservation conditions based on crop type.

## 📁 Project Structure
```text
SeedIQ/
│
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── seediq.db                   # SQLite database (auto-generated)
│
├── static/
│   ├── css/style.css           # Custom green/dark theme with glassmorphism
│   └── images/                 # Image assets
│
├── templates/                  # HTML templates
│   ├── base.html               # Main layout structure
│   ├── login.html              # Authentication
│   ├── register.html
│   ├── dashboard.html          # Interactive charts
│   ├── upload.html             # Dataset upload interface
│   ├── crop_recommendation.html
│   ├── yield_prediction.html
│   ├── seed_viability.html
│   ├── storage_recommendation.html
│   └── quantum_ml.html         # QML explanation
│
├── notebooks/                  # Google Colab Training Scripts
│   ├── 1_Data_Preprocessing.py
│   ├── 2_Classical_ML_Training.py
│   └── 3_Quantum_ML_Training.py
│
├── data/                       # Datasets
│
└── models/                     # Pickled .pkl models
```

## 🛠️ How to Run Locally

### 1. Install Dependencies
Make sure you have Python installed. Run:
```bash
pip install -r requirements.txt
```

### 2. Generate Dummy Data & Models
If you do not want to use Google Colab immediately, you can generate mock data and models by running the scripts in the `notebooks/` directory locally:
```bash
python notebooks/1_Data_Preprocessing.py
python notebooks/2_Classical_ML_Training.py
python notebooks/3_Quantum_ML_Training.py
```
*Note: Qiskit is required to run the Quantum script locally.*

### 3. Start the Flask Server
```bash
python app.py
```
Navigate to `http://localhost:5000` in your web browser.

## ☁️ Google Colab Integration

To train the models on the cloud:
1. Open [Google Colab](https://colab.research.google.com/).
2. Create a new notebook and copy the contents of `notebooks/1_Data_Preprocessing.py`, `notebooks/2_Classical_ML_Training.py`, and `notebooks/3_Quantum_ML_Training.py` into separate cells.
3. Run the cells to train the Random Forest, XGBoost, SVM, and Qiskit VQC models.
4. Download the generated `.pkl` files and place them inside the `models/` directory of this project.
5. The Flask backend will automatically load the exported models.

## 📊 Evaluation & Accuracy Goals
- **Random Forest:** >90%
- **XGBoost:** >92%
- **SVM:** >88%
- **Hybrid VQC Meta Model:** >95%

---
*Built with Flask, scikit-learn, XGBoost, and IBM Qiskit.*
