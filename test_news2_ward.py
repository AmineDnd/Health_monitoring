import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

def main():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        uid = common.authenticate(DB, USER, PASSWORD, {})
        
        # 1. Ensure ICU Ward exists
        icu_wards = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'search_read', [[['ward_type', '=', 'icu']]], {'fields': ['id']})
        icu_id = icu_wards[0]['id'] if icu_wards else False
        if not icu_id:
            print("[FAILED] ICU Ward not found.")
            return

        print(f"[SUCCESS] Found ICU Ward (ID: {icu_id})")

        # 2. Create a Patient assigned to ICU but WITHOUT a specific doctor
        pid = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'NEWS2 Test Patient',
            'ward_id': icu_id,
        }])
        print(f"[SUCCESS] Created Patient without specific doctor (ID: {pid})")

        # 3. Create extreme vitals to trigger NEWS2 > 7
        vid = models.execute_kw(DB, uid, PASSWORD, 'health.vital.record', 'create', [{
            'patient_id': pid,
            'heart_rate': 140, # NEWS2: +3
            'bp_systolic': 85, # NEWS2: +3
            'bp_diastolic': 60,
            'respiratory_rate': 28, # NEWS2: +3
            'spo2': 90, # NEWS2: +3
            'temperature': 39.5, # NEWS2: +2
            'glucose': 100,
            # Total NEWS2: 14 (EMERGENCY)
        }])
        print(f"[SUCCESS] Created Critical Vitals (ID: {vid})")

        # 4. Check the Alert that was generated
        alerts = models.execute_kw(DB, uid, PASSWORD, 'health.alert', 'search_read', [[['patient_id', '=', pid]]], {'fields': ['id', 'assigned_doctor_id', 'parsed_message_html', 'state']})
        if not alerts:
            print("[FAILED] No alert generated.")
            return

        alert = alerts[0]
        if not alert['assigned_doctor_id']:
            print("[SUCCESS] Alert correctly created as UNCLAIMED.")
        else:
            print(f"[FAILED] Alert incorrectly assigned to {alert['assigned_doctor_id']}")
            
        print("\n--- AI HTML MESSAGE ---")
        print(alert['parsed_message_html'])
        
        # 5. Check Ward Counters
        ward = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'search_read', [[['id', '=', icu_id]]], {'fields': ['active_alert_count', 'unclaimed_alert_count']})[0]
        print(f"\n--- WARD METRICS ---")
        print(f"Active Alerts: {ward['active_alert_count']}")
        print(f"Unclaimed Alerts: {ward['unclaimed_alert_count']}")
        
    except Exception as e:
        print(f"[FAILED] Script Error: {e}")

if __name__ == "__main__":
    main()
