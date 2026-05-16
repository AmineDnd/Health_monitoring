import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("--- XML-RPC Odoo Module Upgrade ---")
try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Auth failed.")
        sys.exit(1)
        
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    print("Searching for health_monitoring module...")
    module_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search', [[['name', '=', 'health_monitoring']]])
    
    if not module_ids:
        print("Module not found!")
        sys.exit(1)
        
    module_id = module_ids[0]
    print(f"Found module ID {module_id}. Triggering immediate upgrade...")
    
    # Try immediate upgrade
    try:
        models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_immediate_upgrade', [[module_id]])
        print("Successfully triggered immediate upgrade via XML-RPC!")
    except Exception as e:
        print(f"Direct upgrade button failed: {e}. Trying alternative...")
        models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_upgrade', [[module_id]])
        print("Marked for upgrade. Please go to Apps -> Health Monitoring -> Upgrade in the web UI or restart the server.")
    
except Exception as e:
    print(f"Error: {e}")
