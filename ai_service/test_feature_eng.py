import requests
import json
import time

# Configuration
AI_URL = "http://localhost:8000"

def test_anomaly_with_history():
    print("--- Testing Anomaly Detection with Feature Engineering ---")
    
    # 1. First Reading (Baseline)
    payload_1 = {
        "patient_code": "P123",
        "heart_rate": 75,
        "bp_systolic": 120,
        "bp_diastolic": 80,
        "spo2": 98,
        "temperature": 36.6,
        "respiratory_rate": 16,
        "history": []
    }
    
    print("\n[Step 1] Sending baseline reading (HR=75)...")
    resp1 = requests.post(f"{AI_URL}/analyze", json=payload_1)
    if resp1.status_code != 200:
        print(f"Error: {resp1.text}")
        return
    print(f"Baseline Score: {resp1.json()['anomaly_score']}")

    # 2. Second Reading (Normal Trend)
    history_2 = [payload_1]
    payload_2 = {
        "patient_code": "P123",
        "heart_rate": 78, # Slight increase
        "bp_systolic": 122,
        "bp_diastolic": 82,
        "spo2": 98,
        "temperature": 36.7,
        "respiratory_rate": 17,
        "history": history_2
    }
    
    print("\n[Step 2] Sending second reading (normal trend, HR=78)...")
    resp2 = requests.post(f"{AI_URL}/analyze", json=payload_2)
    print(f"Normal Trend Score: {resp2.json()['anomaly_score']}")

    # 3. Third Reading (Sudden Spike - ANOMALY)
    history_3 = [payload_2, payload_1]
    payload_3 = {
        "patient_code": "P123",
        "heart_rate": 115, # SUDDEN SPIKE (Change = 37 bpm)
        "bp_systolic": 145, # Systolic Spike
        "bp_diastolic": 90,
        "spo2": 94, # Slight drop
        "temperature": 37.5,
        "respiratory_rate": 22,
        "history": history_3
    }
    
    print("\n[Step 3] Sending spike reading (HR 78 -> 115)...")
    resp3 = requests.post(f"{AI_URL}/analyze", json=payload_3)
    data3 = resp3.json()
    print(f"Spike Score: {data3['anomaly_score']}")
    print(f"Is Anomaly: {data3['is_anomaly']}")
    print(f"Message: {data3['message']}")

    # 4. Fourth Reading (SpO2 Drop - ANOMALY)
    history_4 = [payload_3, payload_2, payload_1]
    payload_4 = {
        "patient_code": "P123",
        "heart_rate": 110,
        "bp_systolic": 140,
        "bp_diastolic": 85,
        "spo2": 88, # SUDDEN DROP (94 -> 88)
        "temperature": 37.2,
        "respiratory_rate": 24,
        "history": history_4
    }
    
    print("\n[Step 4] Sending SpO2 drop reading (94 -> 88)...")
    resp4 = requests.post(f"{AI_URL}/analyze", json=payload_4)
    data4 = resp4.json()
    print(f"Drop Score: {data4['anomaly_score']}")
    print(f"Is Anomaly: {data4['is_anomaly']}")
    print(f"Message: {data4['message']}")

if __name__ == "__main__":
    try:
        # Check if service is up
        requests.get(f"{AI_URL}/", timeout=2)
        test_anomaly_with_history()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: AI Service not found at {AI_URL}. Is Docker running?")
