from fastapi import FastAPI

app = FastAPI()

@app.post("/analyze")
def analyze(data: dict):
    if data["heart_rate"] > 120:
        return {"alert": "Rythme cardiaque élevé"}
    if data["temperature"] > 38:
        return {"alert": "Température élevée"}
    if data["spo2"] < 94:
        return {"alert": "Oxygène bas"}
    
    return {"status": "Tout est normal"}
