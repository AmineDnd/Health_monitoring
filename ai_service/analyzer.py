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

def get_dynamic_thresholds(profile: str, age: int) -> tuple:
    """Generate dynamic clinical ranges based on patient lifestyle and age."""
    # Copy baseline ranges
    warning = {k: list(v) for k, v in WARNING_RANGES.items()}
    critical = {k: list(v) for k, v in CRITICAL_RANGES.items()}
    
    profile = profile.lower() if profile else 'standard'
    
    # --- Lifestyle Adjustments ---
    if profile == 'athlete':
        warning['heart_rate'][0] = 45   # Athletes have lower resting HR
        critical['heart_rate'][0] = 35
        warning['bp_systolic'][0] = 85  # Slightly lower BP tolerance
    elif profile == 'pregnant':
        warning['heart_rate'][1] = 110  # Higher resting HR is normal
        warning['bp_systolic'][1] = 135 # Stricter high BP limit (Preeclampsia risk)
    elif profile == 'sedentary':
        warning['heart_rate'][1] = 95   # Less tolerance for high resting HR
    
    # --- Age Adjustments ---
    if 0 < age < 13: # Child
        warning['heart_rate'][1] = 120
        critical['heart_rate'][1] = 140
        warning['respiratory_rate'][1] = 25
        critical['respiratory_rate'][1] = 35
    elif age >= 65: # Elderly
        warning['bp_systolic'][1] = 150 # Higher systolic BP tolerance
        warning['spo2'][0] = 93         # Slightly lower SpO2 tolerance

    # Convert back to tuples
    return {k: tuple(v) for k, v in warning.items()}, {k: tuple(v) for k, v in critical.items()}

def calculate_news2(data: dict) -> tuple:
    """Calculates the National Early Warning Score (NEWS2) based on standard clinical tables."""
    score = 0
    breakdown = []
    
    # 1. Respiration Rate
    rr = data.get('respiratory_rate', 0)
    if rr > 0:
        if rr <= 8: s = 3
        elif 9 <= rr <= 11: s = 1
        elif 12 <= rr <= 20: s = 0
        elif 21 <= rr <= 24: s = 2
        else: s = 3
        score += s
        if s > 0: breakdown.append(f"RR:{s}")

    # 2. SpO2
    spo2 = data.get('spo2', 0)
    if spo2 > 0:
        if spo2 <= 91: s = 3
        elif 92 <= spo2 <= 93: s = 2
        elif 94 <= spo2 <= 95: s = 1
        else: s = 0
        score += s
        if s > 0: breakdown.append(f"SpO2:{s}")

    # 3. Systolic BP
    sbp = data.get('bp_systolic', 0)
    if sbp > 0:
        if sbp <= 90: s = 3
        elif 91 <= sbp <= 100: s = 2
        elif 101 <= sbp <= 110: s = 1
        elif 111 <= sbp <= 219: s = 0
        else: s = 3
        score += s
        if s > 0: breakdown.append(f"SBP:{s}")

    # 4. Heart Rate
    hr = data.get('heart_rate', 0)
    if hr > 0:
        if hr <= 40: s = 3
        elif 41 <= hr <= 50: s = 1
        elif 51 <= hr <= 90: s = 0
        elif 91 <= hr <= 110: s = 1
        elif 111 <= hr <= 130: s = 2
        else: s = 3
        score += s
        if s > 0: breakdown.append(f"HR:{s}")

    # 5. Temperature
    temp = data.get('temperature', 0)
    if temp > 0:
        if temp <= 35.0: s = 3
        elif 35.1 <= temp <= 36.0: s = 1
        elif 36.1 <= temp <= 38.0: s = 0
        elif 38.1 <= temp <= 39.0: s = 1
        else: s = 2
        score += s
        if s > 0: breakdown.append(f"Temp:{s}")

    return score, breakdown

def analyze(input_data: dict) -> dict:
    """Full analysis with missing data handling."""
    history = input_data.get('history', [])
    is_initial = input_data.get('is_initial', False)
    
    # Extract profile data
    profile = input_data.get('lifestyle_profile', 'standard')
    age = input_data.get('age', 0)
    dynamic_warnings, dynamic_criticals = get_dynamic_thresholds(profile, age)
    
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
    for vital, (lo, hi) in dynamic_criticals.items():
        val = data.get(vital, 0)
        if val > 0 and (val < lo or val > hi):
            severity = 'critical'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} CRITICAL, range:{lo}-{hi}]')
            # Calculate how far out it is for more precision
            dist = max(lo - val, val - hi)
            clinical_risk_factor = max(clinical_risk_factor, 0.85 + (dist / (hi if dist > 0 else 1.0) * 0.15))

    for vital, (lo, hi) in dynamic_warnings.items():
        val = data.get(vital, 0)
        already = any(v.startswith(vital) for v in violations)
        if val > 0 and not already and (val < lo or val > hi):
            if severity != 'critical': severity = 'warning'
            violations.append(f'{vital}={val} [{"LOW" if val<lo else "HIGH"} WARNING, normal:{lo}-{hi}]')
            clinical_risk_factor = max(clinical_risk_factor, 0.60)

    # Layer 3: Trend & Change Detection
    significant_changes = []
    dangerous_trends = []
    informational_trends = []
    trend_map = {} # Map vital name to trend string for headline building
    prev = history[0] if history else None
    
    if prev:
        # Define thresholds for reporting changes as DANGEROUS/SIGNIFICANT
        thresholds = {
            'heart_rate': 10,
            'bp_systolic': 15,
            'spo2': 2,
            'glucose': 30,
            'temperature': 0.5,
            'respiratory_rate': 4
        }
        
        for vital, (lo, hi) in dynamic_warnings.items():
            change_key = f"{vital}_change" if vital != 'spo2' else 'spo2_change'
            change = data.get(change_key, 0)
            
            if prev.get(vital, 0) > 0 and data.get(vital, 0) > 0 and change != 0:
                prev_val = prev[vital]
                curr_val = data[vital]
                
                dir_str = "increased" if change > 0 else "decreased"
                if vital == 'spo2' and change < 0: dir_str = "dropped"
                
                unit = "bpm" if vital in ['heart_rate', 'respiratory_rate'] else "mmHg" if "bp" in vital else "mg/dL" if vital == "glucose" else "°C" if vital == "temperature" else "%"
                v_display = VITAL_DISPLAY_NAMES.get(vital, vital.replace('_', ' ').title())
                
                is_improvement = (prev_val < lo or prev_val > hi) and (lo <= curr_val <= hi)
                
                if abs(change) >= thresholds.get(vital, 5) or is_improvement:
                    if is_improvement:
                        status_str = f"STABILIZING: {v_display} improved to {curr_val} {unit} (Normal range: {lo}-{hi})"
                        significant_changes.append(status_str)
                    else:
                        trend_str = f"{v_display} {dir_str} by {abs(change):.1f} {unit}"
                        significant_changes.append(trend_str)
                        dangerous_trends.append(trend_str)
                        trend_map[vital] = f"({dir_str.title()} by {abs(change):.1f} {unit})"
                else:
                    # Provide an explicitly detailed informational breakdown for all other recorded changes
                    trend_str = f"{v_display} {dir_str} by {abs(change):.1f} {unit} (Currently: {curr_val} {unit})"
                    informational_trends.append(trend_str)

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
        
        # CLINICAL ML DISCOUNT: The Isolation Forest was trained on Standard Adults.
        # It will naturally flag Athletes (low HR) or Children (high HR) as anomalous.
        # If there are NO rule-based violations for these profiles, we must suppress the ML false positive.
        if profile != 'standard' or (0 < age < 13):
            if not violations:  # If the dynamic clinical rules say it's fine, trust the rules over the standard ML model
                ml_flagged = False
                ml_base = min(ml_base, 30.0) # Cap score below the 35.0 warning threshold
                
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
    for vital, (lo, hi) in dynamic_warnings.items():
        val = data.get(vital, 0)
        if val <= 0: continue
        rng = hi - lo
        if rng > 0:
            if 0 < (hi - val) / rng < 0.12: trends[vital] = f'approaching upper limit ({val}/{hi})'
            elif 0 < (val - lo) / rng < 0.12: trends[vital] = f'approaching lower limit ({val}/{lo})'

    is_anomaly = bool(violations or dangerous_trends or ml_base > 50)
    
    # Generate Narrative
    narrative = []
    
    # NEW: Calculate NEWS2 Score
    news2_score, news2_breakdown = calculate_news2(data)
    
    # Clinical Recommendations based on NEWS2
    if news2_score >= 7:
        recommendation = "EMERGENCY: Immediate clinical review required. Recommend ICU Transfer."
        if severity != 'critical': severity = 'critical'
    elif news2_score >= 5 or any("3" in b for b in news2_breakdown):
        recommendation = "URGENT: Ward-based medical review required within 1 hour."
        if severity == 'normal': severity = 'warning'
    elif news2_score >= 1:
        recommendation = "MONITOR: Increase vital monitoring frequency."
    else:
        recommendation = "ROUTINE: Continue standard ward monitoring."

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
        
        multi_clause = f" (+{len(violations)-1} other anomalies)" if len(violations) > 1 else ""
        headline = f"{prefix}: {v_display} {v_val}{trend_clause}{multi_clause}"
    elif dangerous_trends:
        headline = f"{prefix}: {dangerous_trends[0]}"
    elif significant_changes:
        # If we reach here with no violations/danger, it's an improvement
        headline = f"{significant_changes[0]}"
    elif ml_base > 50:
        headline = f"ANOMALY: Physiological Pattern Deviation (Score: {anomaly_score:.1f})"
    
    if headline:
        narrative.append(f"SUMMARY:{headline}")

    # 2. NEWS2 Score
    if news2_score > 0:
        narrative.append(f"SYSTEM:Clinical Scoring")
        narrative.append(f"NEWS2 Score: {news2_score} (Breakdown: {', '.join(news2_breakdown)})")
        narrative.append(f"Action: {recommendation}")

    # 3. System Groups
    for sys, vios in system_violations.items():
        if vios:
            narrative.append(f"SYSTEM:{sys}")
            for v in vios:
                # Clean up the internal representation for the UI
                clean_v = v.split('=')[0].replace('_', ' ').strip().title()
                details = v.split('=', 1)[1] if '=' in v else v
                narrative.append(f"{clean_v}: {details}")

    # 4. Trends
    if significant_changes or informational_trends:
        narrative.append("SYSTEM:Chronological Trend Analysis")
        for change in significant_changes:
            narrative.append(f"TREND:{change}")
        for change in informational_trends:
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