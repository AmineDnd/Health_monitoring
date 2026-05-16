"""Warm up DB registry then upgrade module."""
import xmlrpc.client, sys, time

sys.stdout.reconfigure(encoding='utf-8')

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("--- Warming up DB registry ---")
try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    # This call forces Odoo to load the DB into memory
    version = common.version()
    print(f"Server version: {version.get('server_version')}")

    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Auth failed.")
        sys.exit(1)
    print(f"Authenticated uid={uid}")

    time.sleep(2)  # let the registry finish loading

    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

    # Clear asset bundles via ir.attachment
    print("\n--- Clearing asset cache ---")
    att_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.attachment', 'search',
        [[['name', 'like', 'web.assets_'], ['res_model', '=', 'ir.ui.view']]])
    if att_ids:
        models.execute_kw(DB, uid, PASSWORD, 'ir.attachment', 'unlink', [att_ids])
        print(f"Deleted {len(att_ids)} cached asset bundles.")
    else:
        print("No cached bundles found (already clean).")

    # Upgrade module
    print("\n--- Upgrading health_monitoring ---")
    module_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search',
                                   [[['name', '=', 'health_monitoring']]])
    if not module_ids:
        print("Module not found!")
        sys.exit(1)

    module_id = module_ids[0]
    info = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'read',
                             [[module_id]], {'fields': ['state', 'installed_version']})
    print(f"Module state: {info[0]['state']}, version: {info[0]['installed_version']}")

    try:
        models.execute_kw(DB, uid, PASSWORD, 'ir.module.module',
                          'button_immediate_upgrade', [[module_id]])
        print("SUCCESS: Module upgraded!")
    except Exception as e:
        print(f"Immediate upgrade: {e}")
        models.execute_kw(DB, uid, PASSWORD, 'ir.module.module',
                          'button_upgrade', [[module_id]])
        print("Marked for upgrade. Refresh the browser to trigger install.")

except Exception as e:
    print(f"Error: {e}")
