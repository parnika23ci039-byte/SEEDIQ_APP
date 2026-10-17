from sklearn.svm import SVC

def train_seed_model(X, y):
    model = SVC()
    model.fit(X, y)
    return model

def classify_seed(model, sample):
    return model.predict([sample])
