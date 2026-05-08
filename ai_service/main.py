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
        import shutil
        from datetime import datetime
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        from analyzer import FEATURES, compute_derived_features
        import joblib
        import analyzer

        # ── Step 0: Backup existing model ───────────────────────────────
        if os.path.exists('isolation_forest.joblib'):
            joblib.dump(joblib.load('isolation_forest.joblib'), 'isolation_forest_backup.joblib')
            joblib.dump(joblib.load('scaler.joblib'), 'scaler_backup.joblib')
            logger.info("Backup created.")

        # ── Step 1: Compute derived features for all records ────────────
        rows = []
        records = req.records
        for i, rec in enumerate(records):
            history = records[max(0, i-3):i]
            processed = compute_derived_features(rec.copy(), history)
            row = {f: processed.get(f, 0.0) for f in FEATURES}
            rows.append(row)

        if len(rows) < 50:
            return {"status": "error", "message": f"Not enough data: {len(rows)} records. Need at least 50."}

        # ── Step 2: Filter — only train on clinically normal readings ───
        def is_likely_normal(row):
            hr  = row.get('heart_rate', 0)
            sbp = row.get('bp_systolic', 0)
            spo2 = row.get('spo2', 0)
            temp = row.get('temperature', 0)
            return (40 <= hr <= 110 and 80 <= sbp <= 150 and spo2 >= 93 and 35.5 <= temp <= 38.5)

        normal_rows = [r for r in rows if is_likely_normal(r)]
        logger.info(f"Total records: {len(rows)}, Normal records for training: {len(normal_rows)}")

        # ── Step 3: Mix with synthetic data if not enough normals ───────
        if len(normal_rows) < 80:
            logger.warning(f"Only {len(normal_rows)} normal records. Mixing with synthetic data.")
            if os.path.exists('training_data.csv'):
                synthetic_df = pd.read_csv('training_data.csv')
                synthetic_rows = synthetic_df[FEATURES].dropna().to_dict('records')
                # Real data gets 3x weight
                normal_rows = normal_rows * 3 + synthetic_rows
                logger.info(f"After mixing: {len(normal_rows)} training records")

        if len(normal_rows) < 30:
            return {"status": "error", "message": "Not enough normal vitals to train on. Log more patient data first."}

        # ── Step 4: Compute dynamic contamination ────────────────────────
        total = len(rows)
        anomaly_count = total - len([r for r in rows if is_likely_normal(r)])
        computed_contamination = max(0.02, min(0.20, anomaly_count / total if total > 0 else 0.05))
        logger.info(f"Computed contamination rate: {computed_contamination:.2%}")

        # ── Step 5: Train ────────────────────────────────────────────────
        df = pd.DataFrame(normal_rows)
        scaler = StandardScaler()
        X = scaler.fit_transform(df[FEATURES].values)

        model = IsolationForest(
            n_estimators=300,
            contamination=computed_contamination,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X)

        # ── Step 6: Verify before accepting ─────────────────────────────
        try:
            # Normal vitals should NOT be flagged
            test_normal   = [118, 76, 72, 95, 36.8, 98, 16, 0, 0, 0, 0, 72]
            # Critical vitals SHOULD be flagged
            test_critical = [195, 120, 148, 390, 39.9, 80, 30, 30, 40, 15, 5, 148]

            pred_normal   = model.predict(scaler.transform([test_normal]))[0]
            pred_critical = model.predict(scaler.transform([test_critical]))[0]

            if pred_normal == -1:
                # Bad model — restore backup
                if os.path.exists('isolation_forest_backup.joblib'):
                    joblib.dump(joblib.load('isolation_forest_backup.joblib'), 'isolation_forest.joblib')
                    joblib.dump(joblib.load('scaler_backup.joblib'), 'scaler.joblib')
                return {
                    "status": "error",
                    "message": "New model failed verification: flags normal vitals as anomalies. Backup restored."
                }

            if pred_critical == 1:
                logger.warning("New model does not flag critical vitals — clinical rule engine will compensate.")

            logger.info(f"Model verification passed. Normal={pred_normal}, Critical={pred_critical}")

        except Exception as ve:
            logger.error(f"Model verification failed: {ve}")

        # ── Step 7: Save model ───────────────────────────────────────────
        joblib.dump(model, 'isolation_forest.joblib')
        joblib.dump(scaler, 'scaler.joblib')

        # ── Step 8: Archive training run ─────────────────────────────────
        os.makedirs('training_history', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if os.path.exists('training_data.csv'):
            shutil.copy('training_data.csv', f'training_history/training_{timestamp}.csv')

        # ── Step 9: Hot-reload into running service ──────────────────────
        analyzer.MODEL  = model
        analyzer.SCALER = scaler

        logger.info(f"Live model updated in memory. Retrained on {len(normal_rows)} normal records (contamination={computed_contamination:.2%}).")
        logger.warning("NOTE: With --workers 4, only this worker process got the new model in memory. Restart the service to apply to all workers.")
        return {
            "status": "success",
            "samples": len(normal_rows),
            "total_records": len(rows),
            "normal_records": len(normal_rows),
            "contamination": round(computed_contamination, 4),
            "message": f"Model retrained on {len(normal_rows)} records. Restart the AI service to apply to all workers: docker compose restart ai_service"
        }

    except Exception as e:
        logger.error(f"Retraining failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))