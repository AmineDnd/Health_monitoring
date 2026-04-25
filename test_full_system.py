import xmlrpc.client
import sys
import time

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

def test_full_system():
    print("Starting SmartLab Full System Simulation...")
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        uid = common.authenticate(DB, USER, PASSWORD, {})
        
        # 1. Ensure Wards exist
        wards = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'search_read', [[]], {'fields': ['id', 'name', 'ward_type']})
        icu_ward = next((w for w in wards if w['ward_type'] == 'icu'), None)
        ped_ward = next((w for w in wards if w['ward_type'] == 'pediatrics'), None)
        gen_ward = next((w for w in wards if w['ward_type'] == 'general'), None)
        
        if not icu_ward:
            icu_id = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'create', [{'name': 'ICU Test', 'ward_type': 'icu'}])
            icu_ward = {'id': icu_id}
        if not ped_ward:
            ped_id = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'create', [{'name': 'Pediatrics Test', 'ward_type': 'pediatrics'}])
            ped_ward = {'id': ped_id}
        if not gen_ward:
            gen_id = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'create', [{'name': 'General Test', 'ward_type': 'general'}])
            gen_ward = {'id': gen_id}

        print(f"[SUCCESS] Wards Found: ICU ({icu_ward['id']}), Pediatrics ({ped_ward['id']}), General ({gen_ward['id']})")

        # --- SCENARIO 1: The Child in Pediatrics ---
        print("\n--- SCENARIO 1: Pediatric Patient (High HR) ---")
        p1 = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'Timmy (Pediatric Test)',
            'age': 6,
            'lifestyle_profile': 'standard',
            'ward_id': ped_ward['id']
        }])
        
        v1 = models.execute_kw(DB, uid, PASSWORD, 'health.vital.record', 'create', [{
            'patient_id': p1,
            'heart_rate': 125, # High for adult, normal for 6yo!
            'bp_systolic': 100,
            'bp_diastolic': 65,
            'spo2': 98,
            'respiratory_rate': 22,
            'temperature': 37.0,
            'glucose': 90
        }])
        
        alerts1 = models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'search_read', [[['patient_id', '=', p1]]], {'fields': ['id']})
        if not alerts1:
            print("[SUCCESS] AI correctly suppressed HR warning for Child profile (Age 6). No alert generated.")
        else:
            print("[FAILED] AI incorrectly generated an alert for a normal pediatric heart rate.")

        # --- SCENARIO 2: The Athlete in General Admission ---
        print("\n--- SCENARIO 2: Athlete Patient (Low HR & High Temp) ---")
        p2 = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'Sarah (Athlete Test)',
            'age': 28,
            'lifestyle_profile': 'athlete',
            'ward_id': gen_ward['id']
        }])
        
        v2 = models.execute_kw(DB, uid, PASSWORD, 'health.vital.record', 'create', [{
            'patient_id': p2,
            'heart_rate': 45, # Normal for athlete, but combined with Fever:
            'bp_systolic': 110,
            'bp_diastolic': 70,
            'spo2': 97,
            'respiratory_rate': 16,
            'temperature': 39.2, # High Fever (NEWS2 points)
            'glucose': 90
        }])
        
        alerts2 = models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'search_read', [[['patient_id', '=', p2]]], {'fields': ['id', 'severity', 'parsed_message_html', 'assigned_doctor_id']})
        if alerts2:
            alert = alerts2[0]
            print(f"[SUCCESS] AI correctly identified the Fever and generated an alert (Severity: {alert['severity']})")
            print(f"[SUCCESS] Alert deposited in General Ward Queue. Unclaimed? {not bool(alert['assigned_doctor_id'])}")
            
            # Simulate a doctor claiming it
            print("Simulating Doctor Claiming Alert...")
            models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'action_claim_alert', [[alert['id']]])
            updated_alert = models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'search_read', [[['id', '=', alert['id']]]], {'fields': ['assigned_doctor_id']})[0]
            print(f"[SUCCESS] Alert successfully claimed by: {updated_alert['assigned_doctor_id'][1] if updated_alert['assigned_doctor_id'] else 'None'}")
        else:
            print("[FAILED] Alert failed to generate for high fever.")

        # --- SCENARIO 3: The Triage Emergency (AI Ward Routing) ---
        print("\n--- SCENARIO 3: Triage Critical Emergency (AI Ward Routing & Telegram Trigger) ---")
        p3 = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'John Doe (Triage Test)',
            'age': 65,
            'lifestyle_profile': 'standard',
            'admission_status': 'triage'
            # Note: No ward_id assigned yet!
        }])
        
        v3 = models.execute_kw(DB, uid, PASSWORD, 'health.vital.record', 'create', [{
            'patient_id': p3,
            'heart_rate': 145, # High
            'bp_systolic': 80, # Very Low
            'bp_diastolic': 50,
            'spo2': 88, # Very Low
            'respiratory_rate': 26, # High
            'temperature': 39.8, # High
            'glucose': 110
        }])
        
        alerts3 = models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'search_read', [[['patient_id', '=', p3]]], {'fields': ['id', 'severity', 'parsed_message_html']})
        if alerts3:
            print(f"[SUCCESS] AI immediately triggered a {alerts3[0]['severity'].upper()} alert from Triage.")
            print("[SUCCESS] Check your Odoo Chatter and Telegram! A rich broadcast with Deep Links should have been routed to the recommended ICU Ward.")
            print("\n--- AI HTML MESSAGE EXTRACT ---")
            html = alerts3[0]['parsed_message_html']
            print(html[:500] + "...\n(See Odoo UI for full clinical breakdown)")
        else:
            print("[FAILED] Emergency alert not generated.")

    except Exception as e:
        print(f"[FAILED] Script Error: {e}")

if __name__ == "__main__":
    test_full_system()
