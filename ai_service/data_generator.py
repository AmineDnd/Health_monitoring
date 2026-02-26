import numpy as np
import pandas as pd

def generate_normal_vitals(n=5000, random_seed=42):
    """Generate n normal vital readings.
    Parameters from WHO/AHA/ADA clinical guidelines.
    Format: (mean, std_dev, min_clip, max_clip)"""
    rng = np.random.default_rng(random_seed)
    distributions = {
        'bp_systolic':      (115,  11,   88,   142),
        'bp_diastolic':     (75,   8,    58,   90),
        'heart_rate':       (72,   9,    58,   98),
        'glucose':          (92,   13,   68,   128),
        'temperature':      (36.7, 0.28, 36.1, 37.4),
        'spo2':             (98.2, 0.55, 96.2, 100.0),
        'respiratory_rate': (15,   1.8,  11,   19),
    }
    data = {}
    for vital, (mean, std, lo, hi) in distributions.items():
        data[vital] = np.clip(rng.normal(mean, std, n), lo, hi).round(1)
    return pd.DataFrame(data)

if __name__ == '__main__':
    df = generate_normal_vitals()
    df.to_csv('training_data.csv', index=False)
    print(df.describe().round(2))