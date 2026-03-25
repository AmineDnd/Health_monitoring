from analyzer import analyze

def test_clinical_logic():
    print("--- Expanded Clinical Logic Test Suite ---")
    
    # Patient state timeline
    v_normal = {'heart_rate': 72, 'bp_systolic': 120, 'temperature': 36.6, 'spo2': 98, 'glucose': 90, 'respiratory_rate': 16, 'bp_diastolic': 80}
    
    # 1. Baseline
    print("\n[T1] Initial Baseline (Normal)")
    res1 = analyze({**v_normal, 'history': [], 'is_initial': True})
    print(f"Severity: {res1['severity']}, Score: {res1['anomaly_score']}, Anomaly: {res1['is_anomaly']}")
    assert res1['is_anomaly'] == False
    assert res1['anomaly_score'] < 35

    # 2. Critical Event (Temperature 40.5)
    print("\n[T2] Critical Event (Temp 40.5)")
    t2 = v_normal.copy(); t2['temperature'] = 40.5
    res2 = analyze({**t2, 'history': [v_normal], 'is_initial': False})
    print(f"Severity: {res2['severity']}, Score: {res2['anomaly_score']}, Anomaly: {res2['is_anomaly']}")
    assert res2['severity'] == 'critical'
    assert res2['is_anomaly'] == True
    assert res2['anomaly_score'] >= 80

    # 3. Stabilization (Temp 40.5 -> 37.0)
    print("\n[T3] Recovery (Temp returns to 37.0)")
    t3 = v_normal.copy(); t3['temperature'] = 37.0
    res3 = analyze({**t3, 'history': [t2, v_normal], 'is_initial': False})
    print(f"Severity: {res3['severity']}, Score: {res3['anomaly_score']}, Anomaly: {res3['is_anomaly']}")
    print(f"Headline: {res3['message'].split('|')[0]}")
    assert res3['is_anomaly'] == False # Stabilization is NOT an anomaly
    assert res3['anomaly_score'] < 35  # Risk should be LOW now
    assert "STABILIZING" in res3['message']

    # 4. Multiple Issues (Glucose 400 + Heart Rate 135)
    print("\n[T4] Multiple Critical Issues (Glucose 400, HR 135)")
    t4 = v_normal.copy(); t4['glucose'] = 400; t4['heart_rate'] = 135
    res4 = analyze({**t4, 'history': [t3, t2, v_normal], 'is_initial': False})
    print(f"Severity: {res4['severity']}, Score: {res4['anomaly_score']}, Anomaly: {res4['is_anomaly']}")
    assert res4['severity'] == 'critical'
    assert res4['anomaly_score'] >= 85

    # 5. One Issue Resolves (Glucose 110, but HR stays 135)
    print("\n[T5] Partial Stabilization (Glucose 110, but HR 135)")
    t5 = t4.copy(); t5['glucose'] = 110
    res5 = analyze({**t5, 'history': [t4, t3, t2, v_normal], 'is_initial': False})
    print(f"Severity: {res5['severity']}, Score: {res5['anomaly_score']}, Anomaly: {res5['is_anomaly']}")
    print(f"Headline: {res5['message'].split('|')[0]}")
    assert res5['severity'] == 'warning' or res5['severity'] == 'critical' # HR 135 is critical
    assert res5['is_anomaly'] == True # Still have a violation
    assert "STABILIZING: Glucose improved" in res5['message']

    # 6. Complete Recovery
    print("\n[T6] Final Recovery")
    res6 = analyze({**v_normal, 'history': [t5, t4, t3, t2], 'is_initial': False})
    print(f"Severity: {res6['severity']}, Score: {res6['anomaly_score']}, Anomaly: {res6['is_anomaly']}")
    assert res6['is_anomaly'] == False
    assert res6['anomaly_score'] < 35

    print("\nALL CLINICAL TRANSITION TESTS PASSED!")

if __name__ == "__main__":
    test_clinical_logic()
