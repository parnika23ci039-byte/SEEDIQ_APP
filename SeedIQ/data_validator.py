import os
import pandas as pd
import numpy as np

def run_data_quality_checks(filepath, target_col):
    """Performs validation checks on dataset before model training."""
    report = {
        "exists": False,
        "not_empty": False,
        "required_columns_exist": False,
        "target_exists": False,
        "row_count": 0,
        "col_count": 0,
        "missing_count": 0,
        "duplicate_count": 0,
        "infinite_count": 0,
        "constant_columns": [],
        "passed": True,
        "errors": []
    }
    
    if not os.path.exists(filepath):
        report["passed"] = False
        report["errors"].append(f"File not found: {filepath}")
        return report
        
    report["exists"] = True
    
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        report["passed"] = False
        report["errors"].append(f"Failed to read CSV: {e}")
        return report
        
    report["row_count"], report["col_count"] = df.shape
    
    if df.empty or report["row_count"] == 0:
        report["passed"] = False
        report["errors"].append("Dataset is empty.")
        return report
        
    report["not_empty"] = True
    
    if target_col and target_col not in df.columns:
        # Check if case-insensitive match exists
        matches = [c for c in df.columns if c.lower() == target_col.lower()]
        if not matches:
            report["passed"] = False
            report["errors"].append(f"Target column '{target_col}' missing.")
        else:
            report["target_exists"] = True
    else:
        report["target_exists"] = True
        
    report["missing_count"] = int(df.isnull().sum().sum())
    report["duplicate_count"] = int(df.duplicated().sum())
    
    num_df = df.select_dtypes(include=np.number)
    if not num_df.empty:
        report["infinite_count"] = int(np.isinf(num_df).sum().sum())
        
        # Constant columns check
        for col in num_df.columns:
            if num_df[col].nunique() <= 1:
                report["constant_columns"].append(col)
                
    return report

def run_data_leakage_checks(X_train, X_test, y_train, y_test):
    """Checks for train/test data leakage."""
    leakage_report = {
        "train_size": len(X_train),
        "test_size": len(X_test),
        "duplicate_rows_between_splits": 0,
        "passed": True,
        "errors": []
    }
    
    # Check for identical rows in X
    train_df = pd.DataFrame(X_train)
    test_df = pd.DataFrame(X_test)
    
    merged = pd.merge(train_df, test_df, how='inner')
    overlap_count = len(merged)
    leakage_report["duplicate_rows_between_splits"] = overlap_count
    
    if overlap_count > 0:
        leakage_report["passed"] = False
        leakage_report["errors"].append(f"Data leakage detected: {overlap_count} identical sample(s) overlap between train and test sets.")
        
    return leakage_report
