import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

def print_header(title):
    print(f"\n{'='*50}")
    print(f" {title}")
    print(f"{'='*50}")

def main():
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # 1. Admin Login
        admin_uid = common.authenticate(DB, USER, PASSWORD, {})
        if not admin_uid:
            print("[FAILED] Authentication failed for Admin.")
            return

        print_header("1. FETCHING DEMO WELDS & DOCTORS")
        # Fetch the demo wards
        icu_wards = models.execute_kw(DB, admin_uid, PASSWORD, 'health.ward', 'search_read',
            [[['ward_type', '=', 'icu']]], {'fields': ['id', 'name', 'current_occupancy', 'capacity']}
        )
        cardio_wards = models.execute_kw(DB, admin_uid, PASSWORD, 'health.ward', 'search_read',
            [[['ward_type', '=', 'cardiology']]], {'fields': ['id', 'name', 'current_occupancy', 'capacity']}
        )
        
        if not icu_wards or not cardio_wards:
            print("[FAILED] Demo Wards not found. Did you install the demo data?")
            return
            
        icu = icu_wards[0]
        cardio = cardio_wards[0]
        print(f"[SUCCESS] Found ICU: {icu['name']} (Occupancy: {icu['current_occupancy']}/{icu['capacity']})")
        print(f"[SUCCESS] Found Cardiology: {cardio['name']} (Occupancy: {cardio['current_occupancy']}/{cardio['capacity']})")

        print_header("2. TESTING CAPACITY & OCCUPANCY COMPUTATION")
        # Create patients
        p1_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'Test Patient ICU 1',
            'ward_id': icu['id'],
        }])
        p2_id = models.execute_kw(DB, admin_uid, PASSWORD, 'health.patient', 'create', [{
            'name': 'Test Patient Cardio 1',
            'ward_id': cardio['id'],
        }])
        
        # Read wards again to check if occupancy increased
        updated_icu = models.execute_kw(DB, admin_uid, PASSWORD, 'health.ward', 'read', [[icu['id']]], {'fields': ['current_occupancy']})[0]
        
        if updated_icu['current_occupancy'] == icu['current_occupancy'] + 1:
            print(f"[SUCCESS] ICU Occupancy increased automatically to {updated_icu['current_occupancy']}!")
        else:
            print(f"[FAILED] Occupancy did not update. Expected {icu['current_occupancy'] + 1}, got {updated_icu['current_occupancy']}")

        print_header("3. TESTING SECURITY RULES (DATA ISOLATION)")
        
        # FIX PRE-EXISTING DATA: Strip Nurse group from Doctors if they have it
        nurse_group_records = models.execute_kw(DB, admin_uid, PASSWORD, 'ir.model.data', 'search_read',
            [[['module', '=', 'health_monitoring'], ['name', '=', 'group_health_nurse']]],
            {'fields': ['res_id']}
        )
        if nurse_group_records:
            nurse_group_id = nurse_group_records[0]['res_id']
            # Get Dr. House and Dr. Chen user IDs
            doc_users = models.execute_kw(DB, admin_uid, PASSWORD, 'res.users', 'search_read',
                [[['login', 'in', ['gregory.house@hospital.local', 'sarah.chen@hospital.local']]]], {'fields': ['id']}
            )
            for du in doc_users:
                models.execute_kw(DB, admin_uid, PASSWORD, 'res.users', 'write', [[du['id']], {
                    'groups_id': [(3, nurse_group_id)] # 3 means remove
                }])
            print(f"[SUCCESS] Cleaned up legacy Nurse permissions from test doctors.")

        # Login as Dr. House (ICU Doctor)
        house_uid = common.authenticate(DB, "gregory.house@hospital.local", "doctor", {})
        if not house_uid:
            print("[FAILED] Authentication failed for Dr. House.")
            return
            
        house_patients = models.execute_kw(DB, house_uid, "doctor", 'health.patient', 'search_read',
            [[]], {'fields': ['name', 'ward_id']}
        )
        
        # Login as Dr. Chen (Cardiology Doctor)
        chen_uid = common.authenticate(DB, "sarah.chen@hospital.local", "doctor", {})
        chen_patients = models.execute_kw(DB, chen_uid, "doctor", 'health.patient', 'search_read',
            [[]], {'fields': ['name', 'ward_id']}
        )
        
        # Check House's visibility
        house_sees_icu = any(p['id'] == p1_id for p in house_patients)
        house_sees_cardio = any(p['id'] == p2_id for p in house_patients)
        
        print("Dr. House (ICU) sees:")
        for p in house_patients:
            ward_name = p['ward_id'][1] if p['ward_id'] else 'Unassigned'
            print(f"  - {p['name']} (Ward: {ward_name})")
            
        if house_sees_icu and not house_sees_cardio:
            print("[SUCCESS] Dr. House CAN see ICU patients, and CANNOT see Cardiology patients.")
        else:
            print("[FAILED] Security rule leaking for Dr. House.")
            
        # Check Chen's visibility
        print("\nDr. Chen (Cardiology) sees:")
        for p in chen_patients:
            ward_name = p['ward_id'][1] if p['ward_id'] else 'Unassigned'
            print(f"  - {p['name']} (Ward: {ward_name})")
            
        chen_sees_icu = any(p['id'] == p1_id for p in chen_patients)
        chen_sees_cardio = any(p['id'] == p2_id for p in chen_patients)
        
        if chen_sees_cardio and not chen_sees_icu:
            print("[SUCCESS] Dr. Chen CAN see Cardiology patients, and CANNOT see ICU patients.")
        else:
            print("[FAILED] Security rule leaking for Dr. Chen.")

    except Exception as e:
        print(f"[FAILED] Script Error: {e}")

if __name__ == "__main__":
    main()
