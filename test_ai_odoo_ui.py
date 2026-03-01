import sys

env = self.env
try:
    print("--- TESTING ODOO AI FIX WITH MISSING FIELDS ---")
    
    patient = env['health.patient'].create({
        'name': 'UI Blank Check Patient',
        'age': 35,
        'gender': 'male',
    })
    
    print("\n--- SIMULATING UI WITH EMPTY FIELDS ---")
    # For example, they only input heart rate and glucose, leaving others empty (which Odoo passes as False)
    vital = env['health.vital.record'].create({
        'patient_id': patient.id,
        'heart_rate': 160,     # explicitly high to force anomaly
        'glucose': 250,        # explicitly high
        # Everything else missing/False
    })
    print(f"Vital created: ID {vital.id}")
    print(f"AI Score: {vital.ai_score}")
    print(f"Anomaly Detected: {vital.anomaly_detected}")
    print(f"Status: {vital.status}")
    
    env.cr.rollback() # Don't keep test data
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
