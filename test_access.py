import xmlrpc.client

url = "http://localhost:8069"
db = "smartlab_db"
username = "admin" # Main admin
password = "admin" # Assuming default, but let's test

try:
    common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
    uid = common.authenticate(db, username, password, {})
    if not uid:
        print("Could not authenticate as admin. Need to do internal odoo shell test.")
    else:
        print(f"Authenticated admin uid: {uid}")
        
except Exception as e:
    print(f"Error: {e}")
