import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("--- XML-RPC Odoo Set English Language ---")
try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Auth failed.")
        sys.exit(1)
        
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    # Update health_monitoring module to load the translations correctly without the bad comments
    print("Upgrading health_monitoring module to reload translations...")
    module_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search', [[['name', '=', 'health_monitoring']]])
    if module_ids:
        try:
            models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_immediate_upgrade', [module_ids])
            print("Module upgraded successfully.")
        except Exception as e:
            print(f"Direct upgrade failed: {e}. Falling back to mark for upgrade...")
            models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_upgrade', [module_ids])
            print("Module marked for upgrade. Please restart Odoo container.")
    
    # Change Admin user language to English
    print("Setting admin user language to English...")
    models.execute_kw(DB, uid, PASSWORD, 'res.users', 'write', [[uid], {'lang': 'en_US'}])
    print("Successfully set Admin language back to English! Please refresh your browser.")
    
except Exception as e:
    print(f"Error: {e}")
