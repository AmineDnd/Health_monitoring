"""Deep audit of CRITICAL classification + nurse KPI logic."""
import xmlrpc.client

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USER, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

# 1. All patients with their risk data
patients = models.execute_kw(DB, uid, PASSWORD, "health.patient", "search_read",
    [[]], {"fields": ["id", "name", "risk_level", "last_score", "last_alert_id",
                      "admission_status", "vitals_frequency_hours", "last_vital_time"]})
print(f"\n=== PATIENTS ({len(patients)}) ===")
for p in patients:
    alert = f"Alert #{p['last_alert_id'][0]}" if p['last_alert_id'] else "None"
    print(f"  {p['name']:25s} | Risk: {str(p['risk_level']):10s} | Score: {p['last_score']:5.1f} | "
          f"Alert: {alert:12s} | Status: {p['admission_status']:12s} | "
          f"Freq: {p['vitals_frequency_hours']}h | LastVital: {p['last_vital_time']}")

# 2. All alerts
alerts = models.execute_kw(DB, uid, PASSWORD, "health.alert", "search_read",
    [[]], {"fields": ["id", "patient_id", "severity", "state", "headline", "create_date"]})
print(f"\n=== ALERTS ({len(alerts)}) ===")
for a in alerts:
    pname = a['patient_id'][1] if a['patient_id'] else '?'
    print(f"  #{a['id']} | {pname:20s} | Sev: {str(a['severity']):10s} | "
          f"State: {str(a['state']):15s} | {a['headline'][:50]}")

# 3. Recent vitals
vitals = models.execute_kw(DB, uid, PASSWORD, "health.vital.record", "search_read",
    [[]], {"fields": ["id", "patient_id", "heart_rate", "bp_systolic", "bp_diastolic",
                      "spo2", "temperature", "ai_score", "recorded_at"],
           "order": "recorded_at desc", "limit": 20})
print(f"\n=== RECENT VITALS ({len(vitals)}) ===")
for v in vitals:
    pname = v['patient_id'][1] if v['patient_id'] else '?'
    print(f"  #{v['id']} | {pname:20s} | HR:{v['heart_rate']:5.0f} BP:{v['bp_systolic']:3.0f}/{v['bp_diastolic']:3.0f} "
          f"SpO2:{v['spo2']:4.0f} Temp:{v['temperature']:4.1f} | AI:{v['ai_score']:5.1f} | {v['recorded_at']}")

# 4. Nurse KPI diagnosis - simulate the JS logic
print(f"\n=== NURSE KPI SIMULATION ===")
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
admitted = [p for p in patients if p['admission_status'] in ('triage', 'admitted')]
stable = 0; due = 0; overdue = 0; critical = 0
for p in admitted:
    freq = p['vitals_frequency_hours'] or 4
    lvt = p['last_vital_time']
    if lvt:
        # Parse Odoo datetime
        if isinstance(lvt, str):
            lvt = lvt.replace(' ', 'T')
            if not lvt.endswith('Z'):
                lvt += 'Z'
            from datetime import datetime as dt
            last_dt = dt.fromisoformat(lvt.replace('Z', '+00:00'))
        hours = (now - last_dt).total_seconds() / 3600
    else:
        hours = 999

    if p['risk_level'] == 'critical':
        critical += 1
        status = 'critical'
    elif hours >= freq:
        overdue += 1
        status = 'overdue'
    elif hours >= max(freq - 1, freq * 0.75):
        due += 1
        status = 'due_soon'
    else:
        stable += 1
        status = 'up_to_date'

    print(f"  {p['name']:20s} | freq={freq}h | hours={hours:6.1f} | status={status:12s} | risk={p['risk_level']}")

print(f"\n  TOTALS: Critical={critical} Overdue={overdue} DueSoon={due} UpToDate={stable}")
