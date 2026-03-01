import sys

env = self.env
try:
    print("--- TESTING AI INTEGRATION FROM ODOO ---")
    
    # 1. Create Patient
    patient = env['health.patient'].create({
        'name': 'Easy Test Patient C',
        'age': 55,
        'gender': 'female',
    })
    print(f"Patient created: ID {patient.id}")
    
    # 2. Add Normal Vital Record
    print("\n--- NORMAL CASE ---")
    vital_normal = env['health.vital.record'].create({
        'patient_id': patient.id,
        'bp_systolic': 115,
        'bp_diastolic': 75,
        'heart_rate': 72,
        'glucose': 90,
        'temperature': 36.8,
        'spo2': 98,
        'respiratory_rate': 16,
    })
    print(f"Vital created: ID {vital_normal.id}")
    print(f"AI Score: {vital_normal.ai_score}")
    print(f"Anomaly Detected: {vital_normal.anomaly_detected}")
    print(f"Status: {vital_normal.status}")

    # 3. Add Context For Bypass (simulate a UI create where it runs sync)
    print("\n--- CRITICAL CASE ---")
    vital_crit = env['health.vital.record'].create({
        'patient_id': patient.id,
        'bp_systolic': 190,
        'bp_diastolic': 120,
        'heart_rate': 140,
        'glucose': 180,
        'temperature': 40.0,
        'spo2': 85,
        'respiratory_rate': 30,
    })
    print(f"Vital created: ID {vital_crit.id}")
    print(f"AI Score: {vital_crit.ai_score}")
    print(f"Anomaly Detected: {vital_crit.anomaly_detected}")
    print(f"Status: {vital_crit.status}")
    
    # 4. Check if Alert was generated
    alerts = env['health.alert'].search([('patient_id', '=', patient.id)])
    print(f"\nAlerts generated for patient: {len(alerts)}")
    for a in alerts:
        print(f"Alert ID {a.id}, Severity: {a.severity}, Message: {a.message}")
        
    print("\n--- ODOO AI TEST FINISHED ---")
    env.cr.rollback() # Don't keep test data
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
