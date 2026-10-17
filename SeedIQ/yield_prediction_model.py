from xgboost import XGBRegressor

def train_yield_model(X, y):
    model = XGBRegressor()
    model.fit(X, y)
    return model

def predict_yield(model, sample):
    return model.predict([sample])
