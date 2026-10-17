from sklearn.ensemble import RandomForestClassifier

def train_crop_model(X, y):
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X, y)
    return model

def predict_crop(model, sample):
    return model.predict([sample])
