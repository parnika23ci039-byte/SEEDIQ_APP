def recommend_storage(temp, humidity):
    if temp < 20 and humidity < 50:
        return "Ideal Storage Condition"
    else:
        return "Adjust Temperature/Humidity"
