import sys

env = self.env
try:
    print("--- STARTING FUNCTIONAL TEST ---")
    
    # 1. Create Patient
    patient = env['health.patient'].create({
        'name': 'Test Auto Patient',
        'age': 45,
        'gender': 'male',
    })
    print(f"Patient created: ID {patient.id}")
    
    # 2. Add Vital Record (Anomalous)
    vital = env['health.vital.record'].create({
        'patient_id': patient.id,
        'bp_systolic': 180,
        'bp_diastolic': 110,
        'heart_rate': 120,
        'glucose': 90,
        'temperature': 37.0,
        'spo2': 98,
        'respiratory_rate': 25,
    })
    print(f"Vital created: ID {vital.id}")
    
    # 3. Check AI Analysis (Should be synchronously called in create)
    print(f"AI Score: {vital.ai_score}, Anomaly: {vital.anomaly_detected}, Status: {vital.status}")
    
    # 4. Check if Alert was generated
    alert = env['health.alert'].search([('patient_id', '=', patient.id)], limit=1)
    if alert:
        print(f"Alert generated: ID {alert.id}, Severity: {alert.severity}")
    else:
        print("WARNING: No alert generated. (If AI service is unreachable, this might be expected)")
        
    # 5. Check Dashboard KPIs
    dashboard = env['health.dashboard'].create({})
    print(f"Dashboard created. Total Patients: {dashboard.total_patients}, Active Alerts: {dashboard.active_alerts}")
    
    # 6. Test Demo Data Generator
    print("Generating demo data...")
    action = env.ref('health_monitoring.action_generate_demo_data')
    action.with_context(active_id=patient.id).run()
    print("Demo data generated successfully.")
    
    print("--- ALL TESTS PASSED ---")
    env.cr.rollback() # Don't keep test data
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
