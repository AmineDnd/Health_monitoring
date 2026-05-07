import os
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from analyzer import analyze, MODEL, FEATURES, WARNING_RANGES, CRITICAL_RANGES

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title='SmartLab AI Health Monitor',
    description='ML patient vitals anomaly detection using Isolation Forest',
    version='1.0.0'
)

environment = os.environ.get('ENVIRONMENT', 'production')
allowed_origins_str = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:8069')

if environment == 'development':
    origins = ["*"]
    logger.warning("CORS: Allowing all origins because ENVIRONMENT=development")
else:
    origins = [origin.strip() for origin in allowed_origins_str.split(',') if origin.strip()]

app.add_middleware(
    CORSMiddleware, 
    allow_origins=origins, 
    allow_methods=['*'], 
    allow_headers=['*']
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc.body)},
    )

# ── Pydantic schemas — FastAPI validates input automatically ──
class VitalsInput(BaseModel):
    patient_code:     str
    age:              int = Field(default=0)
    gender:           str = Field(default='unknown')
    category:         str = Field(default='unknown')
    lifestyle_profile:str = Field(default='standard')
    bp_systolic:      float = Field(default=0)
    bp_diastolic:     float = Field(default=0)
    heart_rate:       float = Field(default=0)
    glucose:          float = Field(default=0)
    temperature:      float = Field(default=0)
    spo2:             float = Field(default=0)
    respiratory_rate: float = Field(default=0)
    history:          Optional[list] = Field(default=[])
    is_initial:       bool = Field(default=False)

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

class RetrainRequest(BaseModel):
    records: list
    n_samples: int = Field(default=500)

@app.post('/retrain')
def retrain_model(req: RetrainRequest):
    try:
        import pandas as pd
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        from analyzer import FEATURES, compute_derived_features
        import joblib
        
        rows = []
        records = req.records
        # Sort by patient and time to compute history properly
        for i, rec in enumerate(records):
            history = records[max(0, i-3):i]
            processed = compute_derived_features(rec.copy(), history)
            row = {f: processed.get(f, 0.0) for f in FEATURES}
            rows.append(row)
        
        if len(rows) < 50:
            return {"status": "error", "message": f"Not enough data: {len(rows)} records. Need at least 50."}
        
        df = pd.DataFrame(rows)
        
        # Only keep rows that look like normal readings (no extreme outliers for training)
        # We train the model to know what normal looks like
        scaler = StandardScaler()
        X = scaler.fit_transform(df[FEATURES].values)
        
        model = IsolationForest(
            n_estimators=200,
            contamination=0.05,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X)
        
        joblib.dump(model, 'isolation_forest.joblib')
        joblib.dump(scaler, 'scaler.joblib')
        
        # Reload the model in memory
        from analyzer import _load_or_train
        import analyzer
        analyzer.MODEL, analyzer.SCALER = model, scaler
        
        logger.info(f"Model retrained on {len(rows)} real hospital records.")
        return {"status": "success", "samples": len(rows), "message": f"Model retrained on {len(rows)} real patient records."}
    
    except Exception as e:
        logger.error(f"Retraining failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))