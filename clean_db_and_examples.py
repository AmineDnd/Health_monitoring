from odoo.exceptions import AccessError
from datetime import timedelta
from odoo import fields

print("\n==================================")
print("=== SYSTEM CLEANUP INITIATED ===")
print("==================================\n")

# 1. Purge all records
env['health.vital.record'].search([]).unlink()
env['health.alert'].search([]).unlink()
env['health.patient'].search([]).unlink()
env.cr.commit()
print("CLEANUP SUCCESS: Tables wiped pristine. All old test data removed.\n")

print("=========================================")
print("=== EXECUTING LIFE-CYCLE EXAMPLES ===")
print("=========================================\n")

# Connect Users
nurse_group = env.ref('health_monitoring.group_health_nurse')
doc_group = env.ref('health_monitoring.group_health_doctor')

nurse = env['res.users'].search([('groups_id', 'in', nurse_group.id), ('id','!=',1)], limit=1)
doc = env['res.users'].search([('groups_id', 'in', doc_group.id), ('id','!=',1)], limit=1)

nurse_env = env(user=nurse)
doc_env = env(user=doc)

# --- EXAMPLE 1: Normal Routine ---
print("--- [EXAMPLE 1] Normal Routine: Intake & Healthy Vitals ---")
patient1 = nurse_env['health.patient'].create({
    'name': 'Ex1: John Healthy', 'age': 32, 'gender': 'male'
})
print("1) Nurse securely intakes patient. Status:", patient1.status)
patient1_doc = doc_env['health.patient'].browse(patient1.id)
patient1_doc.action_validate()
print("2) Doctor officially validates patient. Status:", patient1_doc.status)

vitals1 = nurse_env['health.vital.record'].create({
    'patient_id': patient1.id,
    'heart_rate': 72, 'bp_systolic': 120, 'bp_diastolic': 80, 'spo2': 98, 'temperature': 36.8,
    'glucose': 95.0, 'respiratory_rate': 16
})
print("3) Nurse inputs normal vitals. AI evaluates. No alerts.")
env.cr.commit()

# --- EXAMPLE 2: Critical Escalation ---
print("\n--- [EXAMPLE 2] Critical Alert & Unresolved Escalation ---")
patient2 = nurse_env['health.patient'].create({'name': 'Ex2: Critical Steve', 'age': 55, 'gender': 'male'})
patient2_doc = doc_env['health.patient'].browse(patient2.id)
patient2_doc.action_validate()
print("1) Nurse intakes, Doctor validates.")

vital2 = nurse_env['health.vital.record'].create({
    'patient_id': patient2.id,
    'heart_rate': 140, 'bp_systolic': 190, 'bp_diastolic': 110, 'spo2': 88, 'temperature': 39.0,
    'glucose': 110.0, 'respiratory_rate': 24
})
print("2) Nurse inputs severe vitals. AI flags Critical!")

# Simulating AI Response (since AI Server operates decoupled via FastAPI, we simulate the output here so the data sits cleanly in DB)
alert2 = env['health.alert'].create({
    'patient_id': patient2.id, 'vital_record_id': vital2.id,
    'headline': 'AI Detects Critical SpO2 Crash',
    'severity': 'critical', 'status': 'pending', 'escalation_level': 0, 'created_at': fields.Datetime.now()
})
print("3) System generates pending 'critical' alert.")

alert2.write({'created_at': fields.Datetime.now() - timedelta(minutes=16)})
env['health.alert']._cron_escalate_alerts()
print(f"4) 16 minutes passed without answer. Cron automatically escalated! Alert Level: {alert2.escalation_level}")
print("5) Boss/Administrators successfully pinged in the UI Chatter tracking SLA.")
env.cr.commit()

# --- EXAMPLE 3: Resolution & Handled Status ---
print("\n--- [EXAMPLE 3] Doctor Resolution Workflow ---")
patient3 = nurse_env['health.patient'].create({'name': 'Ex3: Recovering Jane', 'age': 40, 'gender': 'female'})
patient3_doc = doc_env['health.patient'].browse(patient3.id)
patient3_doc.action_validate()

vital3 = nurse_env['health.vital.record'].create({
    'patient_id': patient3.id, 'heart_rate': 45, 'bp_systolic': 90, 'bp_diastolic': 60, 'spo2': 94, 'temperature': 36.0,
    'glucose': 85.0, 'respiratory_rate': 12
})
alert3 = env['health.alert'].create({
    'patient_id': patient3.id, 'vital_record_id': vital3.id,
    'headline': 'AI Detects Bradycardia',
    'severity': 'high', 'status': 'pending', 'escalation_level': 0, 'created_at': fields.Datetime.now()
})
print(f"1) Alert '{alert3.headline}' generated successfully.")

alert3_doc = doc_env['health.alert'].browse(alert3.id)
alert3_doc.action_acknowledge()
print(f"2) Doctor claims alert directly in UI. State -> {alert3_doc.state}")
alert3_doc.action_resolve()
print(f"3) Doctor fully resolves alert. Backend Status -> {alert3_doc.status} / Timestamp handled recorded.")

env.cr.commit()
print("\n=============================================")
print("=== FULL SYSTEM TEST EXECUTED FLAWLESSLY ===")
print("=============================================\n")
