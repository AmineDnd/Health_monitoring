from datetime import timedelta
from odoo import fields

print("Starting Telegram Escalation Test...")

# Get the Admin user (the user who provided the Telegram ID)
admin = env['res.users'].search([('login', 'in', ['admin', 'admin@example.com'])], limit=1)

# Ensure Admin has Doctor group so they receive the Doctor pings
doc_group = env.ref('health_monitoring.group_health_doctor')
admin.write({'groups_id': [(4, doc_group.id)]})

# Create a test patient assigned to Admin
patient = env['health.patient'].create({
    'name': 'Telegram Test Subject',
    'age': 45,
    'gender': 'male',
    'doctor_id': admin.id,
    'admission_status': 'triage'
})

# Create a vital record (dummy values)
vital = env['health.vital.record'].create({
    'patient_id': patient.id,
    'heart_rate': 150,
    'bp_systolic': 180,
    'bp_diastolic': 110,
    'spo2': 85,
    'temperature': 39.5,
    'glucose': 120.0,
    'respiratory_rate': 28
})

# Generate the Critical Alert (Triggers TIER 0 ping to Doctor Bot)
alert = env['health.alert'].create({
    'patient_id': patient.id,
    'vital_record_id': vital.id,
    'severity': 'critical',
    'status': 'pending',
    'message': 'SUMMARY:Critical Vitals Simulation | SYSTEM:Cardiovascular | TREND:HR increase detected | Action: ICU Admission Immediate'
})
print("Tier 0 Triggered: Sent 'NEW CRITICAL ALERT' to Doctor Bot.")

# Shift time backwards by 6 minutes to simulate delay
alert.write({'created_at': fields.Datetime.now() - timedelta(minutes=6)})
env.cr.commit()

# Trigger Cron (Triggers TIER 1 ping to Doctor Bot)
env['health.alert']._cron_escalate_alerts()
print("Tier 1 Triggered: Sent 'LEVEL 1 ESCALATION' to Doctor Bot.")

# Shift time backwards by 16 minutes to simulate major delay
alert.write({'created_at': fields.Datetime.now() - timedelta(minutes=16)})
env.cr.commit()

# Trigger Cron (Triggers TIER 2 ping to Admin Bot)
env['health.alert']._cron_escalate_alerts()
print("Tier 2 Triggered: Sent 'LEVEL 2 ESCALATION' to Admin Bot.")

print("Test fully executed.")
