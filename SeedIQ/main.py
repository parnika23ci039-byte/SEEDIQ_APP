from data_preprocessing import preprocess_data
from crop_prediction_model import train_crop_model, predict_crop

X, y = preprocess_data("dataset.csv")
model = train_crop_model(X, y)

sample = X[0]
prediction = predict_crop(model, sample)

print("Predicted Crop:", prediction)
