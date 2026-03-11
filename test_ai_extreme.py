import urllib.request
import json

url = "http://localhost:8000/analyze"
data = {
    "patient_code": "extreme_test",
    "bp_systolic": 120.0,
    "bp_diastolic": 80.0,
    "heart_rate": 70.0,
    "glucose": 95.0,
    "temperature": 36.5,
    "spo2": 98.0,
    "respiratory_rate": 80.0  # This was previously rejected (> 60)
}

req = urllib.request.Request(url)
req.add_header('Content-Type', 'application/json; charset=utf-8')
jsondata = json.dumps(data)
jsondataasbytes = jsondata.encode('utf-8')

try:
    response = urllib.request.urlopen(req, jsondataasbytes)
    res_body = response.read().decode('utf-8')
    print(json.dumps(json.loads(res_body), indent=2))
except Exception as e:
    print(f"Error: {e}")
