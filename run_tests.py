"""
SmartLab Automated Tests — runs via Odoo shell piped from stdin.
Usage:  python run_tests.py
"""
import xmlrpc.client, time, sys
from datetime import datetime, timedelta

URL      = "http://localhost:8069"
DB       = "smartlab_db"
USER     = "admin"
PASSWORD = "admin"

# ─── helpers ──────────────────────────────────────────────────────────────────
common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid    = common.authenticate(DB, USER, PASSWORD, {})
if not uid:
    print("AUTH FAILED"); sys.exit(1)
m = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

def call(model, method, args, kw=None):
    return m.execute_kw(DB, uid, PASSWORD, model, method, args, kw or {})

def create(model, vals):
    return call(model, 'create', [vals])

def read(model, ids, fields):
    return call(model, 'read', [ids, fields])

def write(model, ids, vals):
    return call(model, 'write', [[ids], vals])

def search(model, domain):
    return call(model, 'search', [domain])

def unlink(model, ids):
    if ids: call(model, 'unlink', [ids])

def count(model, domain=None):
    return call(model, 'search_count', [domain or []])

def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

results = {}

# ─── TEST 4 — Full AI pipeline ────────────────────────────────────────────────
sep("TEST 4 — FULL AI PIPELINE")

# Step 1: create patient
pid = create('health.patient', {
    'name':              'TEST_AUTO_001',
    'age':               35,
    'gender':            'male',
    'lifestyle_profile': 'standard',
    'status':            'active',
    'admission_status':  'triage',
})
print(f"\n[4-1] Patient created: id={pid}")

# Step 2: normal vitals
now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
vid_n = create('health.vital.record', {
    'patient_id':      pid,
    'bp_systolic':     118, 'bp_diastolic': 76,
    'heart_rate':      72,  'glucose':       92,
    'temperature':     36.8,'spo2':          98,
    'respiratory_rate':16,  'recorded_at':   now_str,
})
print("[4-2] Normal vitals logged — waiting 4s for AI...")
time.sleep(4)

vn = read('health.vital.record', [vid_n], ['ai_score','ai_severity','anomaly_detected'])[0]
alerts_n = count('health.alert', [('patient_id','=',pid),('state','!=','resolved')])
print(f"      ai_score={vn['ai_score']}  severity={vn['ai_severity']}  anomaly={vn['anomaly_detected']}  active_alerts={alerts_n}")

t4a = vn['ai_score'] < 40 and not vn['anomaly_detected'] and alerts_n == 0
results['4A Normal vitals'] = 'PASS' if t4a else 'FAIL'
print(f"      RESULT: {'PASS' if t4a else 'FAIL'}")

# Step 3: critical vitals
time.sleep(1)
now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
vid_c = create('health.vital.record', {
    'patient_id':      pid,
    'bp_systolic':     195, 'bp_diastolic': 118,
    'heart_rate':      148, 'glucose':       390,
    'temperature':     39.9,'spo2':          81,
    'respiratory_rate':30,  'recorded_at':   now_str,
})
print("\n[4-3] Critical vitals logged — waiting 4s for AI...")
time.sleep(4)

vc = read('health.vital.record', [vid_c], ['ai_score','ai_severity','anomaly_detected'])[0]
alert_ids = search('health.alert', [('patient_id','=',pid),('state','!=','resolved')])
print(f"      ai_score={vc['ai_score']}  severity={vc['ai_severity']}  anomaly={vc['anomaly_detected']}  active_alerts={len(alert_ids)}")

t4b = vc['ai_score'] > 60 and vc['anomaly_detected'] and len(alert_ids) > 0
results['4B Critical vitals'] = 'PASS' if t4b else 'FAIL'
print(f"      RESULT: {'PASS' if t4b else 'FAIL'}")

# Step 4: stabilising vitals
time.sleep(1)
now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
vid_s = create('health.vital.record', {
    'patient_id':      pid,
    'bp_systolic':     122, 'bp_diastolic': 80,
    'heart_rate':      76,  'glucose':       98,
    'temperature':     37.0,'spo2':          97,
    'respiratory_rate':16,  'recorded_at':   now_str,
})
print("\n[4-4] Stabilising vitals logged — waiting 4s for AI...")
time.sleep(4)

vs  = read('health.vital.record', [vid_s], ['ai_score','ai_severity','clinical_hints'])[0]
rem = count('health.alert', [('patient_id','=',pid),('state','!=','resolved')])
print(f"      ai_score={vs['ai_score']}  severity={vs['ai_severity']}")
print(f"      clinical_msg={str(vs['clinical_hints'])[:80]}")
print(f"      remaining_active_alerts={rem}")

t4c = rem == 0 and vs['ai_score'] < 50
results['4C Stabilisation'] = 'PASS' if t4c else 'PARTIAL (check STABILIZING msg)'
print(f"      RESULT: {results['4C Stabilisation']}")

# Step 5: discharge
ward_ids = search('health.ward', [])
if ward_ids:
    write('health.patient', pid, {'ward_id': ward_ids[0], 'admission_status': 'admitted'})
test_alert_id = create('health.alert', {
    'patient_id': pid,
    'severity':   'high',
    'message':    'Discharge test alert',
    'state':      'new',
    'status':     'pending',
})
print(f"\n[4-5] Discharge test — alert id={test_alert_id}")

# call action_discharge
call('health.patient', 'action_discharge', [[pid]])
time.sleep(1)

pat   = read('health.patient', [pid], ['admission_status','ward_id'])[0]
al    = read('health.alert',   [test_alert_id], ['state','status'])[0]
print(f"      patient: admission_status={pat['admission_status']}  ward_id={pat['ward_id']}")
print(f"      alert:   state={al['state']}  status={al['status']}")

t4d = (pat['admission_status'] == 'discharged' and
       pat['ward_id'] == False and
       al['state']   == 'resolved' and
       al['status']  == 'handled')
results['4D Discharge'] = 'PASS' if t4d else 'FAIL'
print(f"      RESULT: {'PASS' if t4d else 'FAIL'}")

# cleanup
unlink('health.alert',        search('health.alert',        [('patient_id','=',pid)]))
unlink('health.vital.record', search('health.vital.record', [('patient_id','=',pid)]))
unlink('health.patient', [pid])
print("\n[4] Cleanup done.")

# ─── TEST 5 — SLA response time ───────────────────────────────────────────────
sep("TEST 5 — SLA RESPONSE TIME")

pid5 = create('health.patient', {'name':'TEST_SLA_002','age':45,'gender':'female',
                                  'lifestyle_profile':'standard','status':'active'})
three_min_ago = (datetime.utcnow() - timedelta(minutes=3)).strftime('%Y-%m-%d %H:%M:%S')
now_str       = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

al5 = create('health.alert', {
    'patient_id': pid5, 'severity':'high',
    'message':'SLA test alert', 'state':'new', 'status':'pending',
    'created_at': three_min_ago,
})
before = read('health.alert',[al5],['response_time_minutes'])[0]['response_time_minutes']
print(f"  response_time before resolve: {before} (expected 0)")

write('health.alert', al5, {
    'state':'resolved','status':'handled',
    'handled_at': now_str,
    'resolution_notes':'SLA test',
})
time.sleep(1)
after = read('health.alert',[al5],['response_time_minutes'])[0]['response_time_minutes']
print(f"  response_time after resolve:  {after} (expected ~3.0)")

t5 = 2.5 <= after <= 4.0
results['5 SLA response time'] = 'PASS' if t5 else f'FAIL (got {after})'
print(f"  RESULT: {results['5 SLA response time']}")

unlink('health.alert',  [al5])
unlink('health.patient',[pid5])

# ─── TEST 6 — Concurrent vitals (rapid sequential) ────────────────────────────
sep("TEST 6 — CONCURRENT VITALS (3 patients)")

pids6, vids6 = [], []
for i in range(3):
    p = create('health.patient', {
        'name': f'TEST_CONCURRENT_{i+1:03d}',
        'age': 30 + i*10, 'gender': 'male', 'lifestyle_profile': 'standard', 'status': 'active',
    })
    pids6.append(p)

t0 = time.time()
for i, p in enumerate(pids6):
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    v = create('health.vital.record', {
        'patient_id': p, 'recorded_at': now_str,
        'bp_systolic': 115+i*3,'bp_diastolic':75,'heart_rate':70+i*2,
        'glucose':90,'temperature':36.8,'spo2':97,'respiratory_rate':16,
    })
    vids6.append(v)
elapsed = time.time() - t0
print(f"  3 vitals logged in {elapsed:.1f}s — waiting 5s for AI...")
time.sleep(5)

scored = 0
for v in vids6:
    vr = read('health.vital.record',[v],['ai_score','ai_severity','anomaly_detected'])[0]
    ok = (vr['ai_score'] >= 0 and vr['ai_severity'] != False)
    scored += 1 if ok else 0
    print(f"  vital {v}: score={vr['ai_score']} sev={vr['ai_severity']} anomaly={vr['anomaly_detected']}")

t6a = scored == 3
t6b = elapsed < 30
results['6A All scored']   = 'PASS' if t6a else f'FAIL ({scored}/3 scored)'
results['6B Performance']  = f'PASS ({elapsed:.1f}s)' if t6b else f'SLOW ({elapsed:.1f}s)'
print(f"  RESULT scored: {results['6A All scored']}")
print(f"  RESULT perf:   {results['6B Performance']}")

for v in vids6: unlink('health.vital.record',[v])
for p in pids6: unlink('health.patient',[p])

# ─── TEST 7 — Retrain ─────────────────────────────────────────────────────────
sep("TEST 7 — AI MODEL RETRAIN")

total  = count('health.vital.record')
normal = count('health.vital.record',[('ai_severity','=','normal')])
print(f"  vital records: total={total}  normal={normal}")

t0 = time.time()
ret = call('health.vital.record', 'action_retrain_ai_model', [[]])
elapsed = time.time() - t0
print(f"  retrain call: {elapsed:.1f}s")
print(f"  result type: {ret.get('type')}")

if ret.get('tag') == 'display_notification':
    p = ret.get('params',{})
    print(f"  notification: type={p.get('type')} title={p.get('title')}")
    print(f"  message: {str(p.get('message',''))[:120]}")
    t7 = p.get('type') in ('success','warning')
else:
    print(f"  raw result: {ret}")
    t7 = False

results['7 Retrain'] = 'PASS' if t7 else 'FAIL'
print(f"  RESULT: {results['7 Retrain']}")

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
sep("FINAL SUMMARY")
for k, v in results.items():
    pad = 35 - len(k)
    print(f"  TEST {k}{'.' * pad} {v}")
print()
