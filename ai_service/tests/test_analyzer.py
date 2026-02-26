import sys; sys.path.insert(0, '/app')
from analyzer import analyze

NORMAL   = {'patient_code':'T1','bp_systolic':118,'bp_diastolic':76,'heart_rate':70,
             'glucose':92,'temperature':36.7,'spo2':98,'respiratory_rate':14}
CRITICAL = {'patient_code':'T2','bp_systolic':192,'bp_diastolic':118,'heart_rate':126,
             'glucose':385,'temperature':38.1,'spo2':91,'respiratory_rate':26}

def test_normal_no_anomaly():
    r = analyze(NORMAL)
    assert r['severity'] == 'normal'
    assert 0.0 <= r['anomaly_score'] <= 1.0

def test_critical_vitals():
    r = analyze(CRITICAL)
    assert r['severity'] == 'critical'
    assert r['is_anomaly'] == True
    assert len(r['violations']) > 0

def test_high_glucose_warning():
    r = analyze({**NORMAL, 'glucose': 165})
    assert r['is_anomaly'] == True
    assert any('glucose' in v for v in r['violations'])

def test_low_spo2_critical():
    r = analyze({**NORMAL, 'spo2': 88})
    assert r['severity'] == 'critical'