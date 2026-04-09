import xmlrpc.client

url = 'http://localhost:8069'
db = 'smartlab_db'
username = 'nurse@test.com'
password = '123'

print("--- XML-RPC SIMULATION ---")
try:
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, username, password, {})

    if not uid:
        print("Login Failed: Incorrect database or credentials?")
    else:
        print(f"Remote Login Success! UID: {uid}")
        
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        can_create = models.execute_kw(db, uid, password, 'health.patient', 'check_access_rights', ['create'], {'raise_exception': False})
        print(f"[Network Layer] Can Create: {can_create}")
        
        try:
            print("Attempting to pull form defaults (simulating UI 'New' button click)...")
            defs = models.execute_kw(db, uid, password, 'health.patient', 'default_get', [['name', 'age', 'gender', 'tag_ids', 'doctor_id']])
            print(f"Default Fetch Success: {defs}")
            
            print("Attempting network creation payload...")
            new_id = models.execute_kw(db, uid, password, 'health.patient', 'create', [{'name': 'XML RPC Patient'}])
            print(f"Creation Success! Record ID: {new_id}")
        except xmlrpc.client.Fault as e:
            print(f"CRASH -> {e.faultCode} | {e.faultString}")
            
except Exception as e:
    print(f"Critical Connection Error: {e}")
print("--- END SIMULATION ---")
