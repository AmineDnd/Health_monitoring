import requests
import json

url = "http://localhost:8000/analyze"
payload = {
    "patient_code": "test_patient",
    "bp_systolic": 190,
    "bp_diastolic": 120,
    "heart_rate": 140,
    "glucose": 400,
    "temperature": 40,
    "spo2": 80,
    "respiratory_rate": 35
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")
