import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from analyzer import analyze, MODEL, FEATURES, WARNING_RANGES, CRITICAL_RANGES

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title='SmartLab AI Health Monitor',
    description='ML patient vitals anomaly detection using Isolation Forest',
    version='1.0.0'
)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

# ── Pydantic schemas — FastAPI validates input automatically ──
class VitalsInput(BaseModel):
    patient_code:     str
    bp_systolic:      float = Field(default=0, ge=0, le=300)
    bp_diastolic:     float = Field(default=0, ge=0, le=200)
    heart_rate:       float = Field(default=0, ge=0, le=300)
    glucose:          float = Field(default=0, ge=0, le=1000)
    temperature:      float = Field(default=0, ge=30,  le=45)
    spo2:             float = Field(default=0, ge=0,   le=100)
    respiratory_rate: float = Field(default=0, ge=0,   le=60)

class AnalysisResult(BaseModel):
    patient_code: str; is_anomaly: bool; severity: str
    anomaly_score: float; message: str; violations: list; prediction_1h: dict

# ── Endpoints ─────────────────────────────────────────────────
@app.get('/')
def health_check():
    return {'status':'healthy','service':'SmartLab AI','version':'1.0.0'}

@app.post('/analyze', response_model=AnalysisResult)
def analyze_vitals(vitals: VitalsInput):
    logger.info(f'Analyzing patient: {vitals.patient_code}')
    try:
        result = analyze(vitals.model_dump())
        if result['is_anomaly']:
            logger.warning(f'ANOMALY: {vitals.patient_code} severity={result["severity"]} score={result["anomaly_score"]}')
        return AnalysisResult(patient_code=vitals.patient_code, **result)
    except Exception as e:
        logger.error(f'Analysis failed: {e}')
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/thresholds')
def get_thresholds():
    return {'warning': WARNING_RANGES, 'critical': CRITICAL_RANGES, 'features': FEATURES}

@app.get('/model-info')
def model_info():
    return {'algorithm':'IsolationForest','n_estimators':MODEL.n_estimators,
            'contamination':float(MODEL.contamination),'features':FEATURES}

@app.post('/retrain')
def retrain():
    for f in ['isolation_forest.joblib','scaler.joblib','training_data.csv']:
        if os.path.exists(f): os.remove(f)
    from analyzer import _train_and_save; _train_and_save()
    return {'status':'Model retrained successfully'}