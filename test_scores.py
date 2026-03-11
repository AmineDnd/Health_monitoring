import urllib.request
import json

url = "http://localhost:8000/analyze"

test_cases = [
    {
        "name": "Normal",
        "data": {"patient_code": "T1", "bp_systolic": 115, "bp_diastolic": 75, "heart_rate": 72, "glucose": 90, "temperature": 36.6, "spo2": 98, "respiratory_rate": 16}
    },
    {
        "name": "Critical",
        "data": {"patient_code": "T2", "bp_systolic": 195, "bp_diastolic": 115, "heart_rate": 145, "glucose": 400, "temperature": 40, "spo2": 80, "respiratory_rate": 35}
    },
    {
        "name": "All Zeros (Missing)",
        "data": {"patient_code": "T3", "bp_systolic": 0, "bp_diastolic": 0, "heart_rate": 0, "glucose": 0, "temperature": 0, "spo2": 0, "respiratory_rate": 0}
    }
]

for tc in test_cases:
    print(f"\n--- {tc['name']} ---")
    data = json.dumps(tc['data']).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as f:
            print(json.dumps(json.loads(f.read().decode('utf-8')), indent=2))
    except Exception as e:
        print(f"Error: {e}")
