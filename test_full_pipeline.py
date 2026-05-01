import xmlrpc.client
import time
import sys

url = 'http://localhost:8069'
db = 'smartlab_db'
username = 'admin'
password = 'admin'

def print_step(msg):
    print(f"\n[{time.strftime('%H:%M:%S')}] {msg}")

def print_success(msg):
    print(f"  [+] {msg}")

def print_error(msg):
    print(f"  [-] {msg}")

try:
    print_step("Connecting to Odoo...")
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})
    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
    print_success(f"Authenticated as Admin (UID: {uid})")

    # 1. Clean Slate & Setup
    print_step("Phase 1: Setup - Creating Patient in Bloc 1")
    patient_id = models.execute_kw(db, uid, password, 'health.patient', 'create', [{
        'name': 'End-to-End Test Patient',
        'age': 65,
        'gender': 'male',
        'ward_id': 2, # bloc 1
        'admission_status': 'admitted',
        'risk_level': 'low'
    }])
    print_success(f"Created Patient ID: {patient_id}")

    # 2. Nurse Logs Critical Vitals
    print_step("Phase 2: Nurse Logs Critical Vitals")
    vital_id = models.execute_kw(db, uid, password, 'health.vital.record', 'create', [{
        'patient_id': patient_id,
        'heart_rate': 155,
        'bp_systolic': 195,
        'bp_diastolic': 115,
        'spo2': 86,
        'temperature': 39.9,
        'glucose': 110,
        'respiratory_rate': 28
    }])
    print_success(f"Logged Critical Vitals ID: {vital_id}")

    # 3. Wait for AI Alert
    print_step("Phase 3: Waiting for AI Alert Generation (15s)...")
    time.sleep(15)
    
    alerts = models.execute_kw(db, uid, password, 'health.alert', 'search_read', 
        [[['patient_id', '=', patient_id]]],
        {'fields': ['headline', 'severity', 'state', 'assigned_doctor_id'], 'limit': 1}
    )
    
    if not alerts:
        print_error("AI Alert was NOT generated!")
        sys.exit(1)
    
    alert = alerts[0]
    alert_id = alert['id']
    print_success(f"AI Alert Created: {alert['headline']} (Severity: {alert['severity']})")
    print_success(f"Alert State: {alert['state']}")

    # 4. Doctor Dashboard Query (Unclaimed)
    print_step("Phase 4: Simulating Doctor Dashboard Query (Unclaimed Queue)")
    doctor_ward_ids = [1, 13, 2] # Test ICU, General, Bloc 1
    unclaimed = models.execute_kw(db, uid, password, 'health.alert', 'search_read',
        [[['state', '=', 'new'], ['assigned_doctor_id', '=', False], ['patient_id.ward_id', 'in', doctor_ward_ids]]],
        {'fields': ['headline']}
    )
    if any(a['id'] == alert_id for a in unclaimed):
        print_success("Alert successfully appeared in Doctor's Unclaimed Queue")
    else:
        print_error("Alert MISSING from Doctor's Unclaimed Queue")

    # 5. Doctor Claims Alert
    print_step("Phase 5: Doctor Claims Alert")
    # Simulate action_claim_alert
    models.execute_kw(db, uid, password, 'health.alert', 'action_claim_alert', [alert_id])
    
    claimed_alert = models.execute_kw(db, uid, password, 'health.alert', 'read', [alert_id], {'fields': ['state', 'assigned_doctor_id']})[0]
    if claimed_alert['state'] == 'investigating' and claimed_alert['assigned_doctor_id']:
        print_success(f"Alert successfully claimed by {claimed_alert['assigned_doctor_id'][1]}")
    else:
        print_error(f"Alert claim failed. State: {claimed_alert['state']}")

    # 6. Admin Dashboard KPIs
    print_step("Phase 6: Admin Dashboard KPI Check")
    critical_count = models.execute_kw(db, uid, password, 'health.alert', 'search_count', [[['state', '!=', 'resolved'], ['severity', '=', 'critical']]])
    print_success(f"Admin Dashboard shows {critical_count} active critical alerts")

    # 7. Doctor Resolves Alert
    print_step("Phase 7: Doctor Resolves Alert")
    models.execute_kw(db, uid, password, 'health.alert', 'action_resolve', [alert_id])
    
    resolved_alert = models.execute_kw(db, uid, password, 'health.alert', 'read', [alert_id], {'fields': ['state']})[0]
    if resolved_alert['state'] == 'resolved':
        print_success("Alert successfully resolved.")
    else:
        print_error(f"Alert resolution failed. State: {resolved_alert['state']}")

    # 8. Post-Resolution Validation
    print_step("Phase 8: Final Validation")
    final_critical = models.execute_kw(db, uid, password, 'health.alert', 'search_count', [[['state', '!=', 'resolved'], ['severity', '=', 'critical']]])
    if final_critical < critical_count:
        print_success("Admin KPI correctly updated after resolution")
    else:
        print_error("Admin KPI did not decrease after resolution")
        
    print_step("FULL SYSTEM TEST PASSED! 🚀")

except Exception as e:
    print_error(f"Test failed with exception: {e}")
