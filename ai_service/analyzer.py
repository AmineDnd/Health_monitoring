import os, logging
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

# The 12 features — ORDER matters (must match training data columns)
FEATURES = ['bp_systolic','bp_diastolic','heart_rate','glucose','temperature','spo2','respiratory_rate',
            'heart_rate_change', 'bp_systolic_change', 'bp_diastolic_change', 'spo2_drop_rate', 'moving_avg_hr']

# Clinical thresholds — based on WHO/AHA/ADA guidelines
WARNING_RANGES  = {'bp_systolic':(90,140),'bp_diastolic':(60,90),'heart_rate':(60,100),
                   'glucose':(70,140),'temperature':(36.0,37.5),'spo2':(95,100),'respiratory_rate':(12,20)}
CRITICAL_RANGES = {'bp_systolic':(70,180),'bp_diastolic':(40,120),'heart_rate':(40,130),
                   'glucose':(50,300),'temperature':(35.0,39.5),'spo2':(90,100),'respiratory_rate':(8,30)}

def compute_derived_features(data: dict, history: list) -> dict:
    """Compute temporal features based on previous readings."""
    prev = history[0] if history else None
    
    data['heart_rate_change'] = round(data['heart_rate'] - prev['heart_rate'], 2) if prev else 0.0
    data['bp_systolic_change'] = round(data['bp_systolic'] - prev['bp_systolic'], 2) if prev else 0.0
    data['bp_diastolic_change'] = round(data['bp_diastolic'] - prev['bp_diastolic'], 2) if prev else 0.0
    data['spo2_drop_rate'] = round(max(0, prev['spo2'] - data['spo2']), 2) if prev else 0.0
    
    # Moving average HR (last 3 readings including current)
    hr_values = [data['heart_rate']]
    for h in history[:2]:
        if 'heart_rate' in h:
            hr_values.append(h['heart_rate'])
    
    data['moving_avg_hr'] = round(sum(hr_values) / len(hr_values), 2)
    return data

def _train_and_save():
    logger.info('Training Isolation Forest on synthetic data (with engineered features)...')
    if not os.path.exists('training_data.csv'):
        from data_generator import generate_normal_vitals
        generate_normal_vitals().to_csv('training_data.csv', index=False)
    
    df = pd.read_csv('training_data.csv')
    
    # Verify columns exist
    for f in FEATURES:
        if f not in df.columns:
            logger.warning(f"Feature {f} missing from training data. Re-generating...")
            from data_generator import generate_normal_vitals
            df = generate_normal_vitals()
            df.to_csv('training_data.csv', index=False)
            break

    scaler = StandardScaler()
    X = scaler.fit_transform(df[FEATURES].values)

    model = IsolationForest(n_estimators=200, contamination=0.04, random_state=42, n_jobs=-1)
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

# Load model ONCE
MODEL, SCALER = _load_or_train()

def analyze(input_data: dict) -> dict:
    """Full analysis with missing data handling."""
    history = input_data.get('history', [])
    is_initial = input_data.get('is_initial', False)
    data = compute_derived_features(input_data.copy(), history)
    
    # Check for missing data (0.0)
    critical_vitals = ['bp_systolic', 'heart_rate', 'spo2', 'temperature']
    missing = [v for v in critical_vitals if data.get(v, 0) == 0]
    
    violations = []
    severity = 'normal'
    clinical_risk_factor = 0.0 # 0.0 to 1.0

    if is_initial and len(missing) > 0:
        return {
            'is_anomaly': False,
            'severity': 'normal',
            'anomaly_score': 0.0,
            'message': f"Initial baseline incomplete. Please provide: {', '.join(missing)}",
            'violations': [],
            'prediction_1h': {}
        }

    # Layer 1: Rule-based threshold checks
    for vital, (lo, hi) in CRITICAL_RANGES.items():
        val = data.get(vital, 0)
        if val > 0 and (val < lo or val > hi):
            severity = 'critical'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} CRITICAL, range:{lo}-{hi}]')
            # Calculate how far out it is for more precision
            dist = max(lo - val, val - hi)
            clinical_risk_factor = max(clinical_risk_factor, 0.85 + (dist / (hi if dist > 0 else 1.0) * 0.15))

    for vital, (lo, hi) in WARNING_RANGES.items():
        val = data.get(vital, 0)
        already = any(v.startswith(vital) for v in violations)
        if val > 0 and not already and (val < lo or val > hi):
            if severity != 'critical': severity = 'warning'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} WARNING, normal:{lo}-{hi}]')
            clinical_risk_factor = max(clinical_risk_factor, 0.60)

    # Layer 3: Trend & Change Detection
    significant_changes = []
    prev = history[0] if history else None
    
    if prev:
        hr_change = data.get('heart_rate_change', 0)
        if prev.get('heart_rate', 0) > 0 and data.get('heart_rate', 0) > 0 and abs(hr_change) >= 15:
            dir_str = "increased" if hr_change > 0 else "decreased"
            significant_changes.append(f"Heart Rate {dir_str} by {abs(hr_change):.0f} bpm")
        
        bp_change = data.get('bp_systolic_change', 0)
        if prev.get('bp_systolic', 0) > 0 and data.get('bp_systolic', 0) > 0 and abs(bp_change) >= 20:
            dir_str = "increased" if bp_change > 0 else "decreased"
            significant_changes.append(f"Systolic BP {dir_str} by {abs(bp_change):.0f} mmHg")

        spo2_prev = prev.get('spo2', 0)
        spo2_curr = data.get('spo2', 0)
        if spo2_prev > 0 and spo2_curr > 0 and (spo2_prev - spo2_curr) >= 3:
            significant_changes.append(f"SpO2 dropped by {(spo2_prev - spo2_curr):.1f}%")

    # Layer 2: Isolation Forest ML scoring
    run_ml = len(missing) <= 1
    ml_flagged = False
    ml_base = 0.0
    anomaly_score = 0.0
    
    if run_ml:
        X_input = [data.get(f, 0) for f in FEATURES]
        X_scaled = SCALER.transform([X_input])
        ml_score = MODEL.decision_function(X_scaled)[0]
        # Scaling ML score to 0-70 range
        ml_base = float(np.clip((0.5 - ml_score) * 70, 0, 70))
        ml_pred = MODEL.predict(X_scaled)[0]
        ml_flagged = (ml_pred == -1)
        # Final consolidated score
        anomaly_score = max(ml_base, clinical_risk_factor * 100)
    else:
        # If too much missing data, just set a low neutral score or clinical boost if violations
        anomaly_score = clinical_risk_factor * 100 if violations else 10.0

    if ml_flagged and not violations:
        violations.append(f'ML detected multivariate anomaly (score={anomaly_score:.1f})')
        if severity == 'normal': severity = 'warning'

    # Layer 4: Clinical Narrative & System Grouping
    systems = {
        'Cardiovascular': ['bp_systolic', 'bp_diastolic', 'heart_rate'],
        'Respiratory': ['spo2', 'respiratory_rate'],
        'Metabolic': ['glucose', 'temperature']
    }
    
    system_violations = {sys: [] for sys in systems}
    for vio in violations:
        found_sys = False
        for sys, vitals in systems.items():
            if any(v in vio for v in vitals):
                system_violations[sys].append(vio)
                found_sys = True
                break
        if not found_sys:
            system_violations.setdefault('Other', []).append(vio)

    # Trend warnings: flag vitals approaching their limit
    trends = {}
    for vital, (lo, hi) in WARNING_RANGES.items():
        val = data.get(vital, 0)
        if val <= 0: continue
        rng = hi - lo
        if rng > 0:
            if 0 < (hi - val) / rng < 0.12: trends[vital] = f'approaching upper limit ({val}/{hi})'
            elif 0 < (val - lo) / rng < 0.12: trends[vital] = f'approaching lower limit ({val}/{lo})'

    is_anomaly = bool(violations or ml_base > 50)
    
    # Generate Narrative
    narrative = []
    
    # 1. Headline
    headline = ""
    if severity == 'critical':
        headline = "CRITICAL PATHWAY: Immediate Clinical Review Required"
    elif severity == 'warning':
        headline = "WARNING: System Physiological Instability Detected"
    
    if headline:
        narrative.append(f"SUMMARY:{headline}")

    # 2. System Groups
    for sys, vios in system_violations.items():
        if vios:
            narrative.append(f"SYSTEM:{sys}")
            for v in vios:
                # Clean up the internal representation for the UI
                clean_v = v.split('=')[0].replace('_', ' ').strip().title()
                details = v.split('=', 1)[1] if '=' in v else v
                narrative.append(f"{clean_v}: {details}")

    # 3. Trends
    if significant_changes:
        narrative.append("SYSTEM:Trend Analysis")
        for change in significant_changes:
            narrative.append(f"TREND:{change}")

    if not narrative:
        final_message = "All monitored physiological systems are stable."
    else:
        final_message = " | ".join(narrative)

    return {
        'is_anomaly': is_anomaly,
        'severity': severity,
        'anomaly_score': round(anomaly_score, 4),
        'message': final_message,
        'violations': violations,
        'prediction_1h': trends
    }