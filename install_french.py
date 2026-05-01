import xmlrpc.client
import sys

URL = "http://localhost:8069"
DB = "smartlab_db"
USER = "admin"
PASSWORD = "admin"

print("--- XML-RPC Odoo Install French Language ---")
try:
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASSWORD, {})
    if not uid:
        print("Auth failed.")
        sys.exit(1)
        
    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
    
    # 1. Install French language
    print("Checking for French language (fr_FR)...")
    lang_ids = models.execute_kw(DB, uid, PASSWORD, 'res.lang', 'search', [[['code', '=', 'fr_FR']]])
    if not lang_ids:
        print("French language not active. Checking inactive records...")
        all_lang_ids = models.execute_kw(DB, uid, PASSWORD, 'res.lang', 'search', [[['code', '=', 'fr_FR']]], {'context': {'active_test': False}})
        if all_lang_ids:
            models.execute_kw(DB, uid, PASSWORD, 'res.lang', 'write', [[all_lang_ids[0]], {'active': True}])
            print("Activated French language.")
        else:
            print("Installing French language via wizard...")
            wiz_id = models.execute_kw(DB, uid, PASSWORD, 'base.language.install', 'create', [{'lang': 'fr_FR', 'overwrite': True}])
            models.execute_kw(DB, uid, PASSWORD, 'base.language.install', 'lang_install', [[wiz_id]])
            print("Installed French language.")
    else:
        print("French language is already active.")
        
    # 2. Update health_monitoring module to load the translations
    print("Upgrading health_monitoring module to load translations...")
    module_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search', [[['name', '=', 'health_monitoring']]])
    if module_ids:
        try:
            models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_immediate_upgrade', [module_ids])
            print("Module upgraded successfully.")
        except Exception as e:
            print(f"Direct upgrade failed: {e}. Falling back to mark for upgrade...")
            models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'button_upgrade', [module_ids])
            print("Module marked for upgrade. Please restart Odoo container.")
    
    # 3. Change Admin user language to French
    print("Setting admin user language to French...")
    models.execute_kw(DB, uid, PASSWORD, 'res.users', 'write', [[uid], {'lang': 'fr_FR'}])
    print("Successfully set Admin language to French! Please refresh your browser.")
    
except Exception as e:
    print(f"Error: {e}")
