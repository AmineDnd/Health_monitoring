from analyzer import analyze

def test_trends():
    print("--- Testing Trend Detection Improvements ---")
    
    # 1. Baseline reading
    baseline = {
        'patient_code': 'P001',
        'bp_systolic': 120,
        'bp_diastolic': 80,
        'heart_rate': 70,
        'glucose': 90,
        'temperature': 36.6,
        'spo2': 98,
        'respiratory_rate': 16,
        'history': [],
        'is_initial': True
    }
    
    # 2. Second reading - Heart Rate Increase by 10 (70 -> 80)
    current_hr = {
        'patient_code': 'P001',
        'bp_systolic': 120,
        'bp_diastolic': 80,
        'heart_rate': 80,
        'glucose': 90,
        'temperature': 36.6,
        'spo2': 98,
        'respiratory_rate': 16,
        'history': [baseline],
        'is_initial': False
    }
    
    print("\nCase 1: Heart Rate increase by 10 (70 -> 80)")
    result = analyze(current_hr)
    print(f"Is Anomaly: {result['is_anomaly']}")
    print(f"Severity: {result['severity']}")
    print(f"Message: {result['message']}")
    
    assert result['is_anomaly'] == True
    assert result['severity'] == 'warning'
    assert "Heart Rate increased by 10.0 bpm" in result['message']
    
    # 3. Third reading - Systolic BP Increase by 15 (120 -> 135)
    current_bp = {
        'patient_code': 'P001',
        'bp_systolic': 135,
        'bp_diastolic': 80,
        'heart_rate': 70,
        'glucose': 90,
        'temperature': 36.6,
        'spo2': 98,
        'respiratory_rate': 16,
        'history': [baseline],
        'is_initial': False
    }
    
    print("\nCase 2: Systolic BP increase by 15 (120 -> 135)")
    result = analyze(current_bp)
    print(f"Is Anomaly: {result['is_anomaly']}")
    print(f"Severity: {result['severity']}")
    print(f"Message: {result['message']}")
    
    assert result['is_anomaly'] == True
    assert result['severity'] == 'warning'
    assert "Systolic BP increased by 15.0 mmHg" in result['message']
    
    # 4. Fourth reading - SpO2 drop by 2 (98 -> 96)
    current_spo2 = {
        'patient_code': 'P001',
        'bp_systolic': 120,
        'bp_diastolic': 80,
        'heart_rate': 70,
        'glucose': 90,
        'temperature': 36.6,
        'spo2': 96,
        'respiratory_rate': 16,
        'history': [baseline],
        'is_initial': False
    }
    
    print("\nCase 3: SpO2 drop by 2 (98 -> 96)")
    result = analyze(current_spo2)
    print(f"Is Anomaly: {result['is_anomaly']}")
    print(f"Severity: {result['severity']}")
    print(f"Message: {result['message']}")
    
    assert result['is_anomaly'] == True
    assert result['severity'] == 'warning'
    assert "SpO2 dropped by 2.0 %" in result['message']

    # 5. Fifth reading - Critical Temperature with Trend (36.6 -> 44.0)
    current_crit_temp = {
        'patient_code': 'P001',
        'bp_systolic': 120,
        'bp_diastolic': 80,
        'heart_rate': 70,
        'glucose': 90,
        'temperature': 44.0,
        'spo2': 98,
        'respiratory_rate': 16,
        'history': [baseline],
        'is_initial': False
    }
    
    print("\nCase 4: Critical Temperature with Trend (36.6 -> 44.0)")
    result = analyze(current_crit_temp)
    print(f"Is Anomaly: {result['is_anomaly']}")
    print(f"Severity: {result['severity']}")
    print(f"Message: {result['message']}")
    
    assert result['is_anomaly'] == True
    assert result['severity'] == 'critical'
    # 44.0 - 36.6 = 7.4
    assert "CRITICAL: Temperature 44.0 (Increased by 7.4 °C)" in result['message']

    print("\nALL TESTS PASSED!")

if __name__ == "__main__":
    test_trends()
