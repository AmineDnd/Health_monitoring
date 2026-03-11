import numpy as np
import pandas as pd

def generate_normal_vitals(n_patients=200, readings_per_patient=25, random_seed=42):
    """Generate sequential normal vital readings for multiple patients.
    Includes temporal features: changes and moving averages."""
    rng = np.random.default_rng(random_seed)
    distributions = {
        'bp_systolic':      (115,  8,   100,  135),
        'bp_diastolic':     (75,   6,   60,   85),
        'heart_rate':       (72,   7,   60,   95),
        'glucose':          (92,   10,  70,   120),
        'temperature':      (36.7, 0.2, 36.2, 37.3),
        'spo2':             (98.5, 0.4, 97.0, 100.0),
        'respiratory_rate': (15,   1.5, 12,   18),
    }
    
    all_data = []
    
    for p_id in range(n_patients):
        patient_data = []
        # Initial values for this patient
        current_vitals = {v: rng.normal(mu, sigma) for v, (mu, sigma, lo, hi) in distributions.items()}
        
        for i in range(readings_per_patient):
            # Slow walk / drift for realism
            for v, (mu, sigma, lo, hi) in distributions.items():
                change = rng.normal(0, sigma * 0.2)
                current_vitals[v] = np.clip(current_vitals[v] + change, lo, hi)
            
            row = {v: round(val, 1) for v, val in current_vitals.items()}
            
            # Compute derived features
            if i > 0:
                prev = patient_data[-1]
                row['heart_rate_change'] = round(row['heart_rate'] - prev['heart_rate'], 2)
                row['bp_systolic_change'] = round(row['bp_systolic'] - prev['bp_systolic'], 2)
                row['bp_diastolic_change'] = round(row['bp_diastolic'] - prev['bp_diastolic'], 2)
                row['spo2_drop_rate'] = round(max(0, prev['spo2'] - row['spo2']), 2)
            else:
                row['heart_rate_change'] = 0.0
                row['bp_systolic_change'] = 0.0
                row['bp_diastolic_change'] = 0.0
                row['spo2_drop_rate'] = 0.0
                
            # Moving average HR (last 3 inclusive)
            hr_history = [r['heart_rate'] for r in patient_data[-(3-1):]] + [row['heart_rate']]
            row['moving_avg_hr'] = round(sum(hr_history) / len(hr_history), 2)
            
            patient_data.append(row)
        
        all_data.extend(patient_data)
        
    return pd.DataFrame(all_data)

if __name__ == '__main__':
    df = generate_normal_vitals()
    df.to_csv('training_data.csv', index=False)
    print(f"Generated {len(df)} samples.")
    print(df.head())
    print("\nFeatures:")
    print(df.columns.tolist())