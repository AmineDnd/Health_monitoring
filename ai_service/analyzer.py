import os, logging
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# The 7 features — ORDER matters (must match training data columns)
FEATURES = ['bp_systolic','bp_diastolic','heart_rate','glucose','temperature','spo2','respiratory_rate']

# Clinical thresholds — based on WHO/AHA/ADA guidelines
WARNING_RANGES  = {'bp_systolic':(90,140),'bp_diastolic':(60,90),'heart_rate':(60,100),
                   'glucose':(70,140),'temperature':(36.0,37.5),'spo2':(95,100),'respiratory_rate':(12,20)}
CRITICAL_RANGES = {'bp_systolic':(70,180),'bp_diastolic':(40,120),'heart_rate':(40,130),
                   'glucose':(50,300),'temperature':(35.0,39.5),'spo2':(90,100),'respiratory_rate':(8,30)}

def _train_and_save():
    logger.info('Training Isolation Forest on synthetic data...')
    if not os.path.exists('training_data.csv'):
        from data_generator import generate_normal_vitals
        generate_normal_vitals().to_csv('training_data.csv', index=False)
    df = pd.read_csv('training_data.csv')

    # StandardScaler: normalize all features to mean=0, std=1
    # Needed because glucose (70-400) and temperature (36-40) have very different scales
    scaler = StandardScaler()
    X = scaler.fit_transform(df[FEATURES].values)

    # contamination=0.05: we expect ~5% of real readings to be anomalies
    model = IsolationForest(n_estimators=200, contamination=0.05, random_state=42, n_jobs=-1)
    model.fit(X)

    joblib.dump(model,  'isolation_forest.joblib')
    joblib.dump(scaler, 'scaler.joblib')
    logger.info(f'Model trained on {len(df)} samples and saved.')
    return model, scaler

def _load_or_train():
    if os.path.exists('isolation_forest.joblib') and os.path.exists('scaler.joblib'):
        logger.info('Loading saved model...')
        return joblib.load('isolation_forest.joblib'), joblib.load('scaler.joblib')
    return _train_and_save()

# Load model ONCE at module import time (when FastAPI starts)
MODEL, SCALER = _load_or_train()


def analyze(data: dict) -> dict:
    """Full analysis: rule-based thresholds + Isolation Forest ML."""
    violations = []
    severity = 'normal'

    # Layer 1: Rule-based threshold checks (critical first, then warning)
    for vital, (lo, hi) in CRITICAL_RANGES.items():
        val = data.get(vital, 0)
        if val > 0 and (val < lo or val > hi):
            severity = 'critical'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} CRITICAL, range:{lo}-{hi}]')

    for vital, (lo, hi) in WARNING_RANGES.items():
        val = data.get(vital, 0)
        already = any(v.startswith(vital) for v in violations)
        if val > 0 and not already and (val < lo or val > hi):
            if severity != 'critical': severity = 'warning'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} WARNING, normal:{lo}-{hi}]')

    # Layer 2: Isolation Forest ML scoring
    X = SCALER.transform([[data.get(f, 0) for f in FEATURES]])
    raw_score = float(MODEL.decision_function(X)[0])
    ml_pred   = int(MODEL.predict(X)[0])   # 1=normal, -1=anomaly

    # Map raw_score to 0-1: raw=-0.5 → score=1.0, raw=+0.5 → score=0.0
    anomaly_score = float(np.clip(0.5 - raw_score, 0.0, 1.0))

    ml_flagged = (ml_pred == -1)
    if ml_flagged and not violations:
        violations.append(f'ML detected multivariate anomaly (score={anomaly_score:.3f}) — '
                          'individual values borderline but combination is unusual')
        if severity == 'normal': severity = 'warning'

    # Trend warnings: flag vitals approaching their limit
    trends = {}
    for vital, (lo, hi) in WARNING_RANGES.items():
        val = data.get(vital, 0)
        if val <= 0: continue
        rng = hi - lo
        if rng > 0:
            if 0 < (hi - val) / rng < 0.12: trends[vital] = f'approaching upper limit ({val}/{hi})'
            elif 0 < (val - lo) / rng < 0.12: trends[vital] = f'approaching lower limit ({val}/{lo})'

    is_anomaly = bool(violations) or ml_flagged
    message = (f'[{severity.upper()}] ' + ' | '.join(violations)) if violations else 'All vitals within normal range.'

    return {'is_anomaly':is_anomaly,'severity':severity,'anomaly_score':round(anomaly_score,4),
            'message':message,'violations':violations,'prediction_1h':trends}