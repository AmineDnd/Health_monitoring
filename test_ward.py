import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

# Some environments might have different credentials
# Variables set directly without importing check_db

try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Authentication failed. Check credentials.")
        sys.exit(1)
    
    print(f"Authenticated admin uid: {uid}")
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    # 1. Create a Ward
    print("Creating a new test Ward...")
    ward_id = models.execute_kw(DB, uid, PASSWORD, 'health.ward', 'create', [{
        'name': 'Test Intensive Care Unit',
        'description': 'Main ICU for critical patients'
    }])
    print(f"Ward created with ID: {ward_id}")
    
    # 2. Assign Doctor (Admin is Doctor) and Patient
    print("Creating a Patient assigned to this Ward with Athlete profile...")
    patient_id = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'create', [{
        'name': 'Ward Test Patient',
        'age': 30,
        'gender': 'male',
        'ward_id': ward_id,
        'lifestyle_profile': 'athlete'
    }])
    print(f"Patient created with ID: {patient_id}")
    
    # 3. Read back to confirm
    patient_data = models.execute_kw(DB, uid, PASSWORD, 'health.patient', 'read', [[patient_id]], {'fields': ['name', 'ward_id', 'lifestyle_profile']})
    print(f"Verification Read: {patient_data}")
    
except Exception as e:
    print(f"Test failed or Module Not Upgraded yet: {e}")
    print("Please restart/upgrade your Odoo container to apply the changes.")
