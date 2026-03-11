import sys

env = self.env
try:
    print("--- STARTING COMPREHENSIVE AI INTEGRATION TEST ---")
    
    # Create a fresh patient
    patient = env['health.patient'].create({
        'name': 'Stress Test Patient',
        'age': 45,
        'gender': 'male',
    })
    
    test_cases = [
        {
            'name': 'PERFECTLY NORMAL',
            'data': {
                'bp_systolic': 115, 'bp_diastolic': 75, 'heart_rate': 72,
                'glucose': 90, 'temperature': 36.6, 'spo2': 98, 'respiratory_rate': 16
            },
            'expect_anomaly': False
        },
        {
            'name': 'CRITICAL HYPERTENSION & TACHYCARDIA',
            'data': {
                'bp_systolic': 195, 'bp_diastolic': 115, 'heart_rate': 145,
                'glucose': 100, 'temperature': 37.0, 'spo2': 97, 'respiratory_rate': 18
            },
            'expect_anomaly': True
        },
        {
            'name': 'SPO2 CRITICAL (HYPOXIA)',
            'data': {
                'bp_systolic': 120, 'bp_diastolic': 80, 'heart_rate': 85,
                'glucose': 95, 'temperature': 36.5, 'spo2': 82, 'respiratory_rate': 28
            },
            'expect_anomaly': True
        },
        {
            'name': 'MISSING DATA (Temperature=0)',
            'data': {
                'bp_systolic': 118, 'bp_diastolic': 78, 'heart_rate': 75,
                'glucose': 92, 'temperature': 0.0, 'spo2': 99, 'respiratory_rate': 15
            },
            'expect_anomaly': False
        }
    ]

    for tc in test_cases:
        print(f"\nTesting Case: {tc['name']}")
        vals = tc['data']
        vals['patient_id'] = patient.id
        rec = env['health.vital.record'].create(vals)
        
        print(f"Result -> Anomaly: {rec.anomaly_detected}, Score: {rec.ai_score:.4f}")
        print(f"Message: {rec.clinical_hints}")
        
        if tc['expect_anomaly'] and not rec.anomaly_detected:
            print("!!! WARNING: Expected anomaly but none detected by rules (checking ML score...)")
        
        # Check alerts
        alert = env['health.alert'].search([('vital_record_id', '=', rec.id)], limit=1)
        if alert:
            print(f"Alert Found: {alert.severity} - {alert.message}")
        elif tc['expect_anomaly']:
            print("!!! ERROR: Expected alert but none found")

    print("\n--- COMPREHENSIVE TEST FINISHED ---")
    env.cr.rollback()
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
