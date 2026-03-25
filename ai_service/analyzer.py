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

VITAL_DISPLAY_NAMES = {
    'bp_systolic': 'Systolic BP',
    'bp_diastolic': 'Diastolic BP',
    'heart_rate': 'Heart Rate',
    'glucose': 'Glucose',
    'temperature': 'Temperature',
    'spo2': 'SpO2',
    'respiratory_rate': 'Respiratory Rate'
}

# Clinical thresholds — based on WHO/AHA/ADA guidelines
WARNING_RANGES  = {'bp_systolic':(90,140),'bp_diastolic':(60,90),'heart_rate':(60,100),
                   'glucose':(70,140),'temperature':(36.0,37.5),'spo2':(95,100),'respiratory_rate':(12,20)}
CRITICAL_RANGES = {'bp_systolic':(70,180),'bp_diastolic':(40,120),'heart_rate':(40,130),
                   'glucose':(50,300),'temperature':(35.0,39.5),'spo2':(90,100),'respiratory_rate':(8,30)}

def compute_derived_features(data: dict, history: list) -> dict:
    """Compute temporal features for all vitals."""
    prev = history[0] if history else None
    
    # Core features for ML
    data['heart_rate_change'] = round(data['heart_rate'] - prev['heart_rate'], 2) if prev else 0.0
    data['bp_systolic_change'] = round(data['bp_systolic'] - prev['bp_systolic'], 2) if prev else 0.0
    data['bp_diastolic_change'] = round(data['bp_diastolic'] - prev['bp_diastolic'], 2) if prev else 0.0
    data['spo2_drop_rate'] = round(max(0, prev['spo2'] - data['spo2']), 2) if prev else 0.0
    
    # Generic changes for all vitals to be used in Trends
    if prev:
        data['glucose_change'] = round(data['glucose'] - prev['glucose'], 2)
        data['temperature_change'] = round(data['temperature'] - prev['temperature'], 2)
        data['respiratory_rate_change'] = round(data['respiratory_rate'] - prev['respiratory_rate'], 2)
        data['spo2_change'] = round(data['spo2'] - prev['spo2'], 2)
    else:
        data['glucose_change'] = 0.0
        data['temperature_change'] = 0.0
        data['respiratory_rate_change'] = 0.0
        data['spo2_change'] = 0.0

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
    dangerous_trends = []
    trend_map = {} # Map vital name to trend string for headline building
    prev = history[0] if history else None
    
    if prev:
        # Define thresholds for reporting changes
        thresholds = {
            'heart_rate': 10,
            'bp_systolic': 15,
            'spo2': 2,
            'glucose': 30,
            'temperature': 0.5,
            'respiratory_rate': 4
        }
        
        for vital, threshold in thresholds.items():
            change_key = f"{vital}_change" if vital != 'spo2' else 'spo2_change'
            change = data.get(change_key, 0)
            
            if prev.get(vital, 0) > 0 and data.get(vital, 0) > 0 and abs(change) >= threshold:
                # Check if it was abnormal before and is normal now (Improvement)
                lo, hi = WARNING_RANGES.get(vital, (0, 1000))
                prev_val = prev[vital]
                curr_val = data[vital]
                prev_abnormal = prev_val < lo or prev_val > hi
                curr_normal = lo <= curr_val <= hi
                
                is_improvement = prev_abnormal and curr_normal
                
                dir_str = "increased" if change > 0 else "decreased"
                if vital == 'spo2' and change < 0: dir_str = "dropped"
                
                unit = "bpm" if vital in ['heart_rate', 'respiratory_rate'] else "mmHg" if "bp" in vital else "mg/dL" if vital == "glucose" else "°C" if vital == "temperature" else "%"
                v_display = VITAL_DISPLAY_NAMES.get(vital, vital.replace('_', ' ').title())
                
                if is_improvement:
                    status_str = f"STABILIZING: {v_display} improved to {curr_val} {unit} (Normal range: {lo}-{hi})"
                    significant_changes.append(status_str)
                else:
                    trend_str = f"{v_display} {dir_str} by {abs(change):.1f} {unit}"
                    significant_changes.append(trend_str)
                    dangerous_trends.append(trend_str)
                    trend_map[vital] = f"({dir_str.title()} by {abs(change):.1f} {unit})"

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

    if significant_changes and severity == 'normal':
        severity = 'warning'

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

    is_anomaly = bool(violations or dangerous_trends or ml_base > 50)
    
    # Generate Narrative
    narrative = []
    
    # 1. Headline
    headline = ""
    if severity == 'critical':
        prefix = "CRITICAL"
    elif severity == 'warning':
        prefix = "WARNING"
    else:
        prefix = "STABILIZING" if (significant_changes and not dangerous_trends) else "INFO"

    if violations:
        # Get the first (primary) violation
        prim_vio = violations[0]
        v_name = prim_vio.split('=')[0]
        v_val = prim_vio.split('=')[1].split(' ')[0]
        v_display = VITAL_DISPLAY_NAMES.get(v_name, v_name.replace('_', ' ').title())
        trend_clause = f" {trend_map[v_name]}" if v_name in trend_map else ""
        headline = f"{prefix}: {v_display} {v_val}{trend_clause}"
    elif dangerous_trends:
        headline = f"{prefix}: {dangerous_trends[0]}"
    elif significant_changes:
        # If we reach here with no violations/danger, it's an improvement
        headline = f"{significant_changes[0]}"
    elif ml_base > 50:
        headline = f"ANOMALY: Physiological Pattern Deviation (Score: {anomaly_score:.1f})"
    
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