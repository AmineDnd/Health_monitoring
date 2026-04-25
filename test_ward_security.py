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
        
        # 1. Auth as Admin
        admin_uid = common.authenticate(DB, USER, PASSWORD, {})
        if not admin_uid:
            print("Authentication failed. Check admin credentials.")
            return

        print(f"Authenticated as Admin (uid: {admin_uid})")

        # 2. Setup Doctor Group
        group_records = models.execute_kw(DB, admin_uid, PASSWORD, 'ir.model.data', 'search_read',
            [[['module', '=', 'health_monitoring'], ['name', '=', 'group_health_doctor']]],
            {'fields': ['res_id']}
        )
        if not group_records:
            print("Doctor group not found.")
            return
        doctor_group_id = group_records[0]['res_id']

        # Helper to create/get user
        def setup_doc(name, login, password):
            user_records = models.execute_kw(DB, admin_uid, PASSWORD, 'res.users', 'search_read',
                [[['login', '=', login]]], {'fields': ['id']}
            )
            if user_records:
                user_id = user_records[0]['id']
                print(f"Doctor {login} exists (id: {user_id})")
                # Ensure they have doctor group and base group
                models.execute_kw(DB, admin_uid, PASSWORD, 'res.users', 'write', [[user_id], {
                    'password': password,
                    'groups_id': [(4, doctor_group_id), (4, 1)]
                }])
            else:
                user_id = models.execute_kw(DB, admin_uid, PASSWORD, 'res.users', 'create', [{
                    'name': name,
                    'login': login,
                    'password': password,
                    'groups_id': [(4, doctor_group_id), (4, 1)]
                }])
                print(f"Created Doctor {login} (id: {user_id})")
            return user_id

        doc1_id = setup_doc("Dr. House (Cardio)", "house@test.com", "123")
        doc2_id = setup_doc("Dr. Strange (Neuro)", "strange@test.com", "123")

        # 3. Create Wards
        print("\nCreating Wards...")
        ward1_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.ward', 'create', [{
            'name': 'Cardiology Department',
            'doctor_ids': [(4, doc1_id)]
        }])
        ward2_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.ward', 'create', [{
            'name': 'Neurology Department',
            'doctor_ids': [(4, doc2_id)]
        }])
        print(f"Cardio Ward ID: {ward1_id}")
        print(f"Neuro Ward ID: {ward2_id}")

        # 4. Create Patients
        print("\nCreating Patients...")
        patient1_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'John Heart',
            'age': 45,
            'ward_id': ward1_id,
            'lifestyle_profile': 'sedentary'
        }])
        patient2_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'Jane Brain',
            'age': 32,
            'ward_id': ward2_id,
            'lifestyle_profile': 'standard'
        }])
        print(f"Patient John Heart ID: {patient1_id}")
        print(f"Patient Jane Brain ID: {patient2_id}")

        # 5. Test Access Rights for Dr. House
        print("\nTesting Access for Dr. House (house@test.com)...")
        doc1_uid = common.authenticate(DB, "house@test.com", "123", {})
        doc1_patients = models.execute_kw(DB, doc1_uid, "123", 'health.patient', 'search_read',
            [[]], {'fields': ['name', 'ward_id']}
        )
        print(f"Dr. House sees {len(doc1_patients)} patients:")
        for p in doc1_patients:
            print(f" - {p['name']} (Ward ID: {p['ward_id']})")
        
        # Verify Dr. House sees John Heart but not Jane Brain
        sees_john = any(p['id'] == patient1_id for p in doc1_patients)
        sees_jane = any(p['id'] == patient2_id for p in doc1_patients)
        if sees_john and not sees_jane:
            print("[SUCCESS] Ward Security Rule for Dr. House")
        else:
            print("[FAILED] Ward Security Rule for Dr. House")

        # 6. Test Access Rights for Dr. Strange
        print("\nTesting Access for Dr. Strange (strange@test.com)...")
        doc2_uid = common.authenticate(DB, "strange@test.com", "123", {})
        doc2_patients = models.execute_kw(DB, doc2_uid, "123", 'health.patient', 'search_read',
            [[]], {'fields': ['name', 'ward_id']}
        )
        print(f"Dr. Strange sees {len(doc2_patients)} patients:")
        for p in doc2_patients:
            print(f" - {p['name']} (Ward ID: {p['ward_id']})")
        
        sees_john_2 = any(p['id'] == patient1_id for p in doc2_patients)
        sees_jane_2 = any(p['id'] == patient2_id for p in doc2_patients)
        if sees_jane_2 and not sees_john_2:
            print("[SUCCESS] Ward Security Rule for Dr. Strange")
        else:
            print("[FAILED] Ward Security Rule for Dr. Strange")

        # 7. Test AI Connection (Add Vital Record for John Heart)
        print("\nTesting AI pipeline with a new vital record for John Heart...")
        try:
            vital_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.vital.record', 'create', [{
                'patient_id': patient1_id,
                'heart_rate': 140, # High HR to trigger AI
                'bp_systolic': 160,
                'bp_diastolic': 100,
                'temperature': 39.5,
                'spo2': 90,
                'glucose': 90,
                'respiratory_rate': 25
            }])
            print(f"Vital Record created! ID: {vital_id}")
            
            # Re-read patient to check if AI assigned a risk score
            updated_patient = models.execute_kw(DB, admin_uid, PASSWORD, 'health.patient', 'read', [[patient1_id]], {'fields': ['last_score', 'risk_level']})
            print(f"John Heart's updated AI Risk Info: {updated_patient[0]}")
            if updated_patient[0]['last_score'] > 0:
                 print("[SUCCESS] AI Pipeline test")
            else:
                 print("[FAILED] AI Pipeline test: AI didn't return a score.")
                 
        except Exception as e:
            print(f"[FAILED] AI Pipeline test: {e}")

    except Exception as e:
        print(f"Script Error: {e}")

if __name__ == "__main__":
    main()
