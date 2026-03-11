import urllib.request
import json

url = "http://localhost:8000/analyze"
data = {
    "patient_code": "test_patient_v4",
    "bp_systolic": 190.0,
    "bp_diastolic": 120.0,
    "heart_rate": 140.0,
    "glucose": 400.0,
    "temperature": 0.0,  # This was the problematic value
    "spo2": 80.0,
    "respiratory_rate": 35.0
}

req = urllib.request.Request(url)
req.add_header('Content-Type', 'application/json; charset=utf-8')
jsondata = json.dumps(data)
jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
req.add_header('Content-Length', len(jsondataasbytes))

try:
    response = urllib.request.urlopen(req, jsondataasbytes)
    res_body = response.read().decode('utf-8')
    print(json.dumps(json.loads(res_body), indent=2))
except Exception as e:
    print(f"Error: {e}")
