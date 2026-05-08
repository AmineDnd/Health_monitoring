import xmlrpc.client

URL = "http://localhost:8069"
DB = "health_monitor"

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')

# Try to find who's logged in
print("Trying common passwords...")
for pw in ['admin', 'Admin', 'admin1', '1234', 'odoo', 'Odoo']:
    try:
        uid = common.authenticate(DB, 'admin', pw, {})
        if uid:
            print(f"SUCCESS: admin / {pw}  -> uid={uid}")
            break
        else:
            print(f"FAIL: admin / {pw}")
    except Exception as e:
        print(f"ERROR: {e}")
