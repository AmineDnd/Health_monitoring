import urllib.request
import json
import time

AI_URL = "http://localhost:8000"

def test_profile(name, payload, expected_severity=None):
    print(f"\n--- Testing Profile: {name} ---")
    print(f"Age: {payload.get('age', 0)}, Lifestyle: {payload.get('lifestyle_profile', 'standard')}")
    print(f"Vitals: HR={payload.get('heart_rate')}, BP={payload.get('bp_systolic')}/{payload.get('bp_diastolic')}")
    
    try:
        start_time = time.time()
        
        req = urllib.request.Request(f"{AI_URL}/analyze", data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode())
            
        duration = time.time() - start_time
        
        severity = result.get('severity')
        score = result.get('anomaly_score')
        message = result.get('message')
        
        print(f"Result: {severity.upper()} (Score: {score}) in {duration*1000:.1f}ms")
        print(f"Message: {message}")
        
        if expected_severity:
            if severity == expected_severity:
                print(f"[SUCCESS] PASSED (Expected: {expected_severity})")
            else:
                print(f"[FAILED] FAILED (Expected: {expected_severity}, Got: {severity})")
                
    except Exception as e:
        print(f"[FAILED] Error: {e}")

if __name__ == "__main__":
    print("Testing Dynamic AI Thresholds...")
    
    # 1. Athlete with Low HR (48) - Should be NORMAL
    test_profile("Athlete Low HR", {
        "patient_code": "TEST-1",
        "age": 25,
        "lifestyle_profile": "athlete",
        "heart_rate": 48,
        "bp_systolic": 110,
        "bp_diastolic": 70,
        "glucose": 90,
        "temperature": 36.5,
        "spo2": 98,
        "respiratory_rate": 15,
        "is_initial": True
    }, expected_severity="normal")
    
    # 2. Standard Adult with same Low HR (48) - Should be CRITICAL (below 60 warning, below 50 maybe critical but let's see. Normal HR ranges: Warn < 60, Crit < 40. Wait, 48 is < 60 so it should be WARNING. Wait, Crit < 40. Let's see what the AI says, but it should NOT be normal.)
    test_profile("Standard Low HR", {
        "patient_code": "TEST-2",
        "age": 30,
        "lifestyle_profile": "standard",
        "heart_rate": 48,
        "bp_systolic": 110,
        "bp_diastolic": 70,
        "glucose": 90,
        "temperature": 36.5,
        "spo2": 98,
        "respiratory_rate": 15,
        "is_initial": True
    }, expected_severity="warning")
    
    # 3. Pregnant with High BP (138) - Should be WARNING (Since limit was lowered to 135)
    test_profile("Pregnant Borderline High BP", {
        "patient_code": "TEST-3",
        "age": 28,
        "lifestyle_profile": "pregnant",
        "heart_rate": 80,
        "bp_systolic": 138,
        "bp_diastolic": 80,
        "glucose": 90,
        "temperature": 36.8,
        "spo2": 98,
        "respiratory_rate": 15,
        "is_initial": True
    }, expected_severity="warning")
    
    # 4. Standard Adult with same BP (138) - Should be NORMAL (Since limit is 140)
    test_profile("Standard Borderline High BP", {
        "patient_code": "TEST-4",
        "age": 35,
        "lifestyle_profile": "standard",
        "heart_rate": 80,
        "bp_systolic": 138,
        "bp_diastolic": 80,
        "glucose": 90,
        "temperature": 36.8,
        "spo2": 98,
        "respiratory_rate": 15,
        "is_initial": True
    }, expected_severity="normal")
    
    # 5. Child with High HR (115) - Should be NORMAL (Limit is 120)
    test_profile("Child High HR", {
        "patient_code": "TEST-5",
        "age": 8,
        "lifestyle_profile": "standard",
        "heart_rate": 115,
        "bp_systolic": 100,
        "bp_diastolic": 60,
        "glucose": 90,
        "temperature": 36.8,
        "spo2": 98,
        "respiratory_rate": 20,
        "is_initial": True
    }, expected_severity="normal")
    
    # 6. Standard Adult with High HR (115) - Should be WARNING/CRITICAL (Limit is 100)
    test_profile("Standard High HR", {
        "patient_code": "TEST-6",
        "age": 40,
        "lifestyle_profile": "standard",
        "heart_rate": 115,
        "bp_systolic": 100,
        "bp_diastolic": 60,
        "glucose": 90,
        "temperature": 36.8,
        "spo2": 98,
        "respiratory_rate": 20,
        "is_initial": True
    }, expected_severity="warning")
